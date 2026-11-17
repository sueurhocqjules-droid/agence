"""Pilote : le seul agent qui décide. Une séance Claude Code (web, fichiers, commandes) qui avance vers l'objectif de
organisation/MISSION.md, puis un script qui garde ce qui est sûr et vert.

    python -m agence.pilote seance              séance Claude dans ce dépôt (et chaines-studio/ à côté)
    python -m agence.pilote trier               étape suivante, sans clé : tests verts ou code retiré, studio qui compile
    python -m agence.pilote publier <paquet>    sur le main à jour : applique le paquet sans les fichiers protégés,
                                                verdict du juge, coût, guichet, message à Jules, relance éventuelle
    python -m agence.pilote studio              retire du patch du studio ce qui le pousse ou le publie

Le workflow `.github/workflows/pilote.yml` enchaîne les quatre. `publier` est lancé depuis le main, avant le patch :
ses modules (protégés) sont chargés avant, et les fichiers protégés du patch sont remis comme au main avant toute
autre chose. Le code écrit par le Pilote n'exécute donc jamais le contrôle qui le juge.

Règle de deux : la séance lit le web [A] mais n'a aucun secret [B] (seul son propre jeton, illisible par ses
commandes) et n'agit dehors [C] qu'à travers ce script. Quatre garde-fous, pas plus (MISSION.md) : aucune clé
visible, fichiers protégés changés seulement sur un Oui de Jules, code gardé seulement si les tests passent, et
l'anti-emballement (Veille, ci-dessous). La relecture du code par un modèle gratuit est un avis du juge, pas un tri.
"""
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from agence import guichet, lancer, organisation, registre, telegram

POSTE = "pilote"
RACINE = Path(__file__).resolve().parent.parent
STUDIO = RACINE / "chaines-studio"            # copie de travail du studio (ignorée par Git dans ce dépôt)
CARNET = RACINE / "registre" / "pilote"
RAPPORT = CARNET / "rapport.json"              # écrit par la séance : message à Jules, demandes au guichet
PASSAGE = CARNET / "passage.json"              # écrit par ce script : coût et sort des changements
VERDICT = RACINE / "registre" / "juge" / "verdict.json"   # avis du juge sur la séance précédente
MODELE = "claude-opus-5-5"
TOURS_MAX = 5000                               # garde-fou technique, pas une limite de travail
DUREE_MAX_S = 320 * 60                         # un job GitHub s'arrête à 6 h : de quoi trier et publier après
OUTILS = "Read,Edit,Write,Glob,Grep,Bash,WebSearch,WebFetch,TodoWrite,Agent"   # Agent : sous-agents ponctuels
# Prix Opus publics par million de jetons, pour estimer le coût d'une séance coupée avant son résultat
PRIX = {"input_tokens": 5, "output_tokens": 25, "cache_creation_input_tokens": 6.25, "cache_read_input_tokens": 0.5}
ECRITURES = ("Edit", "Write", "NotebookEdit", "MultiEdit")
# Jamais gardés depuis une séance : ce qui fixe ses propres limites et ce qui la contrôle. Une demande au guichet
# les fait changer par Jules (avec Claude dans Jarvis).
PROTEGES = (
    ".github/",
    "organisation/MISSION.md",
    "organisation/seuils.toml",
    "organisation/autorisations.toml",
    "organisation/scripts.toml",
    "agence/pilote.py",
    "agence/lancer.py",
    "agence/juge.py",
    "agence/tableau.py",          # mesures lues par le juge et par Jules, lancé avec des clés
    "agence/relecture.py",
    "agence/equipe.py",
    "agents/surete.py",
    # Modules chargés par `publier`, qui tourne avec le jeton d'écriture et Telegram
    "agence/__init__.py",
    "agence/guichet.py",
    "agence/organisation.py",
    "agence/registre.py",
    "agence/telegram.py",
    "agence/modeles.py",
    "tests/test_pilote.py",
    "tests/test_equipe.py",
    "tests/test_surete.py",
    "tests/test_juge.py",
    "tests/test_tableau.py",
)
# Le registre est écrit par les scripts du réveil : la séance n'y écrit que dans registre/pilote/ (son carnet)
REGISTRE, CARNET_REL = "registre/", "registre/pilote/"
# Dans le studio : ce qui tourne avec les clés de déploiement au moment de pousser vers studio-rendu
STUDIO_PROTEGES = (".github/", "scripts/synchro_rendu.py")
CODE = (".py", ".js", ".ts", ".tsx", ".sh", ".yml", ".yaml")


def _sous(chemin, prefixes):
    return any(chemin == p or (p.endswith("/") and chemin.startswith(p)) for p in prefixes)


def protege(chemin):
    return _sous(chemin, PROTEGES) or (chemin.startswith(REGISTRE) and not chemin.startswith(CARNET_REL))


def _git(dossier, *args, check=True):
    return subprocess.run(["git", "-C", str(dossier), *args], capture_output=True, text=True, encoding="utf-8",
                          check=check).stdout


def changements(dossier):
    """Chemins modifiés, ajoutés ou supprimés depuis le dernier commit (fichiers non suivis compris)."""
    _git(dossier, "add", "-A", "--intent-to-add")
    sortie = _git(dossier, "status", "--porcelain", "--untracked-files=all")
    chemins = []
    for ligne in sortie.splitlines():
        chemin = ligne[3:].split(" -> ")[-1].strip().strip('"')
        if chemin:
            chemins.append(chemin)
    return chemins


def defaire(dossier, chemins):
    """Remet ces chemins comme au dernier commit (un fichier nouveau est retiré)."""
    for chemin in chemins:
        suivi = subprocess.run(["git", "-C", str(dossier), "cat-file", "-e", f"HEAD:{chemin}"],
                               capture_output=True).returncode == 0
        if suivi:
            _git(dossier, "checkout", "HEAD", "--", chemin)
        else:
            _git(dossier, "rm", "-q", "--cached", "--ignore-unmatch", "--", chemin, check=False)
            p = Path(dossier) / chemin
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
            elif p.exists() or p.is_symlink():
                p.unlink()


# --- Budget et rythme ------------------------------------------------------------------------------------------

def rythme():
    with open(organisation.DOSSIER / "rythme.toml", "rb") as f:
        return tomllib.load(f).get("pilote", {})


def plafond_seance(maintenant, couts, atelier, reglages, reglage_rythme):
    """(plafond en $ de cette séance, dépensé cette semaine, part de la semaine en $ ou None pendant le lancement).
    Le plafond d'une séance est l'anti-emballement (seance_max_pourcent de la limite hebdomadaire), borné par ce qui
    reste de la part de la semaine. usd_max_seance (rythme.toml) ne compte que si le Pilote le choisit."""
    from agents import surete   # import tardif : surete importe ce module par questions → lancer
    depense = surete.compteur(maintenant, couts, atelier, reglages)["hors_reserve"]
    cl, em = reglages["claude"], reglages["emballement"]
    plafond = float(em["seance_max_pourcent"]) * float(cl["dollars_par_pourcent"])
    part = surete.part_semaine(maintenant, reglages)
    if part is not None:
        plafond = min(plafond, part - depense)
    if reglage_rythme.get("usd_max_seance"):
        plafond = min(plafond, float(reglage_rythme["usd_max_seance"]))
    return max(0.0, plafond), depense, part


# --- Anti-emballement ------------------------------------------------------------------------------------------

class Veille:
    """Garde-fou 4 (MISSION.md) : lit le flux de la séance (stream-json) et dit quand l'arrêter. Pas de plafond de
    travail : seulement une boucle (même action en échec), une séance qui ne produit plus rien, la réserve de Jules
    et une séance qui avale à elle seule une trop grosse part de la semaine."""

    def __init__(self, debut, emballement, reserve_pourcent, duree_max_s=DUREE_MAX_S):
        self.debut = self.derniere_ecriture = debut
        self.echecs_max = int(emballement["echecs_identiques_max"])
        self.sans_ecrire_s = 60 * float(emballement["minutes_sans_ecrire_max"])
        self.seance_max = float(emballement["seance_max_pourcent"]) / 100
        self.utilisation_max = 1 - float(reserve_pourcent) / 100
        self.duree_max_s = duree_max_s
        self.appels = {}            # id d'appel d'outil → (outil, entrée en bref)
        self.echec, self.serie = None, 0
        self.usages = {}            # id de message → usage, pour estimer le coût d'une séance coupée
        self.utilisation_debut = self.utilisation = None
        self.ecritures, self.resultat = 0, None

    def lire(self, evt, t):
        """Un événement du flux. Renvoie la raison d'arrêter, sinon None."""
        quoi = evt.get("type")
        if quoi == "assistant":
            message = evt.get("message") or {}
            if message.get("id") and isinstance(message.get("usage"), dict):
                self.usages[message["id"]] = message["usage"]
            for bloc in message.get("content") or []:
                if isinstance(bloc, dict) and bloc.get("type") == "tool_use":
                    entree = json.dumps(bloc.get("input"), ensure_ascii=False, sort_keys=True)[:300]
                    self.appels[bloc.get("id")] = (bloc.get("name"), entree)
                    if bloc.get("name") in ECRITURES:
                        self.derniere_ecriture, self.ecritures = t, self.ecritures + 1
        elif quoi == "user":
            for bloc in (evt.get("message") or {}).get("content") or []:
                if not (isinstance(bloc, dict) and bloc.get("type") == "tool_result"):
                    continue
                if not bloc.get("is_error"):
                    self.echec, self.serie = None, 0
                    continue
                action = self.appels.get(bloc.get("tool_use_id"), ("?", ""))
                self.serie = self.serie + 1 if action == self.echec else 1
                self.echec = action
                if self.serie >= self.echecs_max:
                    return f"la même action a échoué {self.serie} fois de suite ({action[0]} {action[1][:150]})"
        elif quoi == "rate_limit_event":
            fenetres = (evt.get("rate_limit_info") or {}).get("unifiedWindows") or {}
            u = (fenetres.get("seven_day") or {}).get("utilization")
            if isinstance(u, (int, float)) and not isinstance(u, bool):
                if self.utilisation_debut is None:
                    self.utilisation_debut = u
                self.utilisation = u
                if u >= self.utilisation_max:
                    return f"réserve de Jules atteinte : {u:.0%} de sa limite hebdomadaire utilisés"
                if u - self.utilisation_debut >= self.seance_max:
                    return f"cette séance a utilisé plus de {self.seance_max:.0%} de la limite hebdomadaire"
        elif quoi == "result":
            self.resultat = evt
        return None

    def verifier(self, t):
        """Ce qui se juge à l'horloge. Renvoie la raison d'arrêter, sinon None."""
        if t - self.derniere_ecriture >= self.sans_ecrire_s:
            return f"{self.sans_ecrire_s / 60:.0f} minutes sans rien écrire"
        if t - self.debut >= self.duree_max_s:
            return f"séance coupée après {self.duree_max_s / 60:.0f} minutes (fin du créneau GitHub)"
        return None

    def cout_estime(self):
        return sum(PRIX[k] * float(u.get(k) or 0) for u in self.usages.values() for k in PRIX) / 1e6


# --- Séance ----------------------------------------------------------------------------------------------------

def demandes_ouvertes():
    """Demandes du guichet en attente de Jules, en texte court pour la consigne (GitHub illisible : dit tel quel)."""
    try:
        demandes = guichet.ouvertes()
    except Exception as e:
        return f"illisibles ({type(e).__name__})"
    return "\n".join(f"#{d['numero']} {d['titre']} (depuis le {d['date'][:10]})" for d in demandes) or "aucune"


def _lire(chemin, defaut, n):
    try:
        return chemin.read_text(encoding="utf-8")[:n]
    except OSError:
        return defaut


def consigne(maintenant, plafond, depense, part, reglages, ouvertes="aucune"):
    cl, em = reglages["claude"], reglages["emballement"]
    if part is None:
        budget = (f"carte blanche jusqu'au {cl['lancement_jusqu_au']:%d/%m %H:%M} UTC, la seule limite est de laisser "
                  f"{cl['reserve_pourcent']} % de la limite hebdomadaire à Jules ({depense:.2f} $ dépensés cette semaine)")
    else:
        budget = (f"{depense:.2f} $ dépensés cette semaine sur {part:.0f} $ "
                  f"({cl['part_pourcent']} % de la limite hebdomadaire de Jules)")
    return f"""Tu es le Pilote de l'agence. Lis d'abord organisation/PILOTE.md (ton mode d'emploi), puis
organisation/MISSION.md, puis ton carnet registre/pilote/carnet.md s'il existe. Ensuite, fais avancer l'agence vers
l'objectif, jusqu'au bout de ce que tu peux faire dans cette séance.

Nous sommes le {maintenant:%Y-%m-%d %H:%M} UTC. La semaine de l'abonnement commence le vendredi à 23 h UTC.
Budget Claude : {budget}.
Cette séance s'arrête d'elle-même à {plafond:.2f} $, après {DUREE_MAX_S // 60} minutes, si la même action échoue
{em['echecs_identiques_max']} fois de suite, ou après {em['minutes_sans_ecrire_max']} minutes sans écrire de fichier :
note tes trouvailles au fil de l'eau dans ton carnet, et garde de quoi écrire ton rapport avant la fin.

Demandes au guichet qui attendent Jules (ne les redemande pas, ferme celles qui ne servent plus) :
{ouvertes[:3000]}

Ce que le script a fait du résultat de ta séance précédente :
{_lire(PASSAGE, "aucun (première séance)", 6000)}

Avis du juge (un modèle gratuit, séparé de toi) sur ta séance précédente :
{_lire(VERDICT, "aucun pour l'instant", 4000)}"""


def arreter(proc):
    proc.terminate()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def seance_claude(texte, plafond, veille, ouvrir=subprocess.Popen, horloge=time.monotonic):
    """Lance Claude Code à la racine du dépôt, sous la Veille. Renvoie {ok, resume, cout, jetons, tours, erreur,
    arret, utilisation, ecritures}."""
    commande = ["claude", "-p", "--model", MODELE, "--output-format", "stream-json", "--verbose",
                "--max-turns", str(TOURS_MAX), "--max-budget-usd", f"{plafond:.2f}", "--tools", OUTILS,
                "--allowedTools", OUTILS, "--permission-mode", "dontAsk", "--strict-mcp-config",
                "--setting-sources", "", "--no-session-persistence", "--add-dir", str(STUDIO)]
    # Claude ne reçoit que son propre jeton, et ses commandes ne le voient pas (environnement nettoyé)
    env = lancer.env_cloisonne(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN"}) | {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1",
                                                                           "PYTHONUTF8": "1"}
    lignes, arret = queue.Queue(), None
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as erreurs:
        proc = ouvrir(commande, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=erreurs, text=True,
                      encoding="utf-8", errors="replace", cwd=str(RACINE), env=env)

        def lire():
            for ligne in proc.stdout:
                lignes.put(ligne)
            lignes.put(None)

        threading.Thread(target=lire, daemon=True).start()
        try:
            proc.stdin.write(texte)
            proc.stdin.close()
        except OSError:
            pass
        while True:
            try:
                ligne = lignes.get(timeout=30)
            except queue.Empty:
                ligne = ""
            if ligne is None:
                break
            evt = None
            if ligne.strip():
                try:
                    evt = json.loads(ligne)
                except ValueError:
                    pass
            t = horloge()
            arret = (veille.lire(evt, t) if isinstance(evt, dict) else None) or veille.verifier(t)
            if arret:
                print(f"Anti-emballement : {arret}", flush=True)
                arreter(proc)
                break
        proc.wait()
        erreurs.seek(0)
        stderr = erreurs.read()[-400:]
    r = veille.resultat or {}
    usage = r.get("usage") or {}
    jetons = sum(int(u.get(k) or 0) for u in ([usage] if usage else veille.usages.values()) for k in PRIX)
    cout = float(r.get("total_cost_usd") or 0) or veille.cout_estime()
    ok = (not arret and proc.returncode == 0 and bool(r) and not r.get("is_error")
          and r.get("subtype", "success") == "success")
    if arret:
        erreur = f"arrêt anti-emballement : {arret}"
    elif ok:
        erreur = None
    else:
        erreur = (f"séance arrêtée ({r.get('subtype') or f'code {proc.returncode}'}) : "
                  f"{str(r.get('result') or stderr)[-400:]}")
    return {"ok": ok, "resume": str(r.get("result") or ""), "cout": round(cout, 4), "jetons": jetons,
            "tours": r.get("num_turns"), "erreur": erreur, "arret": arret, "utilisation": veille.utilisation,
            "ecritures": veille.ecritures}


# --- Tri du résultat (job de la séance, sans clé) ---------------------------------------------------------------

def tests_verts():
    """Tests du dépôt, sans aucune clé dans l'environnement : ils exécutent le code de la séance."""
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-q", "tests"], cwd=str(RACINE),
                          capture_output=True, text=True, encoding="utf-8",
                          env=lancer.env_cloisonne(os.environ, set()) | {"PYTHONUTF8": "1"})
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-1500:]


def trier_agence():
    """Protégés retirés, code gardé seulement si les tests passent. Renvoie le bilan pour le passage."""
    bilan = {"proteges_retires": [], "code_retire": [], "tests": "aucun code"}
    chemins = changements(RACINE)
    proteges = [c for c in chemins if protege(c)]
    if proteges:
        defaire(RACINE, proteges)
        bilan["proteges_retires"] = proteges
    code = [c for c in chemins if c not in proteges and (c.endswith(CODE) or c.startswith("tests/"))]
    if code:
        ok, detail = tests_verts()
        bilan["tests"] = "verts" if ok else f"rouges, code retiré : {detail}"
        if not ok:
            defaire(RACINE, code)
            bilan["code_retire"] = code
    bilan["gardes"] = [c for c in changements(RACINE) if not c.startswith("registre/pilote/passage")]
    return bilan


def trier_studio():
    """Garde les sujets complets qui compilent dans chaines-studio, sinon défait tout le studio."""
    if not STUDIO.exists():
        return {"studio": "absent"}
    # Pas de changements() avant tri_atelier.py : il ne regarde que les fichiers non suivis par Git
    if not _git(STUDIO, "status", "--porcelain", "--untracked-files=all").strip():
        return {"studio": "rien de neuf"}
    env = lancer.env_cloisonne(os.environ, set())
    for etape in (["python3", "scripts/tri_atelier.py"], ["npm", "run", "lint"]):
        proc = subprocess.run(etape, cwd=str(STUDIO), capture_output=True, text=True, encoding="utf-8", env=env)
        if proc.returncode:
            defaire(STUDIO, changements(STUDIO))
            return {"studio": f"retiré, `{' '.join(etape)}` en échec : {(proc.stdout + proc.stderr)[-1200:]}"}
    manquants = sujets_incomplets(STUDIO)
    if manquants:
        defaire(STUDIO, changements(STUDIO))
        return {"studio": f"retiré, sujets incomplets : {', '.join(manquants)[:1200]}"}
    return {"studio": "gardé", "studio_fichiers": changements(STUDIO)[:200]}


def sujets_incomplets(dossier):
    """Sujets du studio auxquels manque un des cinq fichiers (atelier/CONSIGNES.md)."""
    dossier = Path(dossier)
    manquants = []
    for f in sorted((dossier / "sujets").glob("*.json")):
        if f.name.endswith(".calcul.json"):
            continue
        n = f.stem
        for requis in (f"sujets/{n}.calcul.json", f"public/sons/{n}.wav", f"src/scenes/{n}/index.tsx",
                       f"scripts/calcul_{n}.py"):
            if not (dossier / requis).exists():
                manquants.append(f"{n} ({requis})")
    return manquants


def lire_rapport():
    """Message à Jules, demandes au guichet, demandes à fermer et souhait de relance (rapport.json), sûrs à envoyer."""
    vide = {"message_jules": "", "demandes": [], "fermer": [], "relancer": False}
    try:
        rapport = json.loads(RAPPORT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return vide
    if not isinstance(rapport, dict):
        return vide
    demandes, fermer = [], []
    for d in (rapport.get("demandes") or [])[:10]:
        if isinstance(d, dict) and d.get("titre") and d.get("quoi"):
            demandes.append({k: guichet.sans_mention(d.get(k), 1500) for k in ("titre", "quoi", "pourquoi", "debloque",
                                                                                 "lien", "cout")}
                            | {"urgent": bool(d.get("urgent"))})
    for f in (rapport.get("fermer") or [])[:20]:
        if isinstance(f, dict) and str(f.get("numero", "")).isdigit():
            fermer.append({"numero": int(f["numero"]), "raison": guichet.sans_mention(f.get("raison") or "obsolète", 500)})
    return {"message_jules": guichet.sans_mention(rapport.get("message_jules"), 1500), "demandes": demandes,
            "fermer": fermer, "relancer": rapport.get("relancer") is True}


def seance():
    maintenant = datetime.now(timezone.utc)
    pause = lancer.pause_active([POSTE, lancer.TOUT], registre.lire("pauses"))
    if pause:
        print(f"Pilote en pause ({pause['cible']}, par {pause['par']} : {pause['raison']})")
        return 0
    from agents import surete
    reglages = surete.seuils()
    plafond, depense, part = plafond_seance(maintenant, registre.lire("couts"), surete.couts_atelier(), reglages,
                                            rythme())
    if plafond < 1:
        print(f"Budget de la semaine atteint : {depense:.2f} $ sur {part or 0:.0f} $, pas de séance")
        return 0
    CARNET.mkdir(parents=True, exist_ok=True)
    RAPPORT.unlink(missing_ok=True)
    debut = registre.maintenant()
    veille = Veille(time.monotonic(), reglages["emballement"], reglages["claude"]["reserve_pourcent"])
    s = seance_claude(consigne(maintenant, plafond, depense, part, reglages, demandes_ouvertes()), plafond, veille)
    rapport = lire_rapport()
    RAPPORT.unlink(missing_ok=True)       # lu une fois : ne repart pas à la séance suivante
    passage = {"debut": debut, "fin": registre.maintenant(), "cout_usd": s["cout"], "jetons": s["jetons"],
               "tours": s["tours"], "erreur": s["erreur"], "arret": s["arret"], "utilisation": s["utilisation"],
               "ecritures": s["ecritures"], "resume": s["resume"][-3000:], **rapport, "trie": False}
    PASSAGE.write_text(json.dumps(passage, ensure_ascii=False, indent=1), encoding="utf-8")
    _sortie_github(faite="oui")
    return 0


def trier():
    """Après la séance, dans une étape à part et sans clé."""
    passage = json.loads(PASSAGE.read_text(encoding="utf-8"))
    passage |= trier_agence() | trier_studio() | {"trie": True}
    PASSAGE.write_text(json.dumps(passage, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in passage.items() if k != "resume"}, ensure_ascii=False, indent=1))
    _sortie_github(studio="oui" if passage.get("studio") == "gardé" else "non")
    return 0


def _sortie_github(**valeurs):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.writelines(f"{k}={v}\n" for k, v in valeurs.items())


# --- Publication (job qui écrit, lancé depuis le main avant le patch) ---------------------------------------------

def appliquer(dossier, patch, interdits):
    """Applique le patch de la séance, puis remet comme au dernier commit tout chemin interdit. Renvoie les chemins
    remis. Lève RuntimeError si le patch ne s'applique pas."""
    patch = Path(patch)
    if patch.exists() and patch.stat().st_size:
        for options in ([], ["--3way"]):
            proc = subprocess.run(["git", "-C", str(dossier), "apply", "--index", *options, str(patch)],
                                  capture_output=True, text=True, encoding="utf-8")
            if proc.returncode == 0:
                break
        else:
            raise RuntimeError(f"patch non appliqué : {proc.stderr[-300:]}")
    remis = [c for c in changements(dossier) if interdits(c)]
    defaire(dossier, remis)
    return remis


def message_jules(passage, message, verdict=None):
    lignes = [f"Pilote : séance finie ({passage['cout_usd']:.2f} $)."]
    if passage.get("erreur"):
        lignes.append(f"Arrêt : {passage['erreur'][:300]}")
    if message:
        lignes.append(message)
    retire = passage.get("proteges_retires", []) + passage.get("code_retire", [])
    if retire:
        lignes.append(f"Non gardé ({len(retire)} fichiers) : {', '.join(retire[:5])}")
    if str(passage.get("studio", "")).startswith("retiré"):
        lignes.append("Vidéos de la séance retirées : le studio ne compilait pas.")
    if verdict:
        lignes.append(f"Juge ({'?' if verdict.get('note') is None else verdict['note']}/10) : {str(verdict.get('resume', ''))[:600]}")
        if verdict.get("code") == "a_revoir":
            lignes.append(f"⚠️ Code gardé à revoir : {str(verdict.get('code_detail', ''))[:500]}")
    return "\n\n".join(lignes)[:3500]


def fermer_demandes(fermer, gh=None):
    """Ferme les demandes que le Pilote juge obsolètes, seulement parmi les demandes ouvertes du guichet (ni une PR,
    ni une autre issue). Renvoie les numéros fermés."""
    gh = gh or guichet._gh
    if not fermer:
        return []
    try:
        ouvertes = {d["numero"] for d in guichet.ouvertes(gh) if not d["pr"]}
    except Exception as e:
        print(f"Guichet illisible, rien fermé : {type(e).__name__}")
        return []
    fermees = []
    for f in fermer:
        if f["numero"] not in ouvertes:
            continue
        try:
            gh("issue", "close", str(f["numero"]), "-R", guichet.DEPOT, "--comment", f"Fermée par le Pilote : {f['raison']}")
            fermees.append(f["numero"])
        except Exception as e:
            print(f"Guichet : #{f['numero']} non fermée ({type(e).__name__})")
    return fermees


def duree_s(passage):
    return round((datetime.fromisoformat(passage["fin"]) - datetime.fromisoformat(passage["debut"])).total_seconds())


def relancer(passage):
    """Le Pilote enchaîne une autre séance s'il l'a demandé, et seulement après une séance saine : aucun arrêt ni
    erreur, et au moins 10 minutes (sinon une séance qui échoue vite boucle). Le budget est revu par la séance."""
    return bool(passage.get("relancer")) and not passage.get("erreur") and duree_s(passage) >= 600


def noter(passage, verdict=None):
    """Coût, journal, demandes au guichet et message à Jules, à partir du passage de la séance."""
    ouvertes = []
    for d in passage.get("demandes", []):
        try:
            numero, _ = guichet.demander(d["titre"], d["quoi"], d["pourquoi"], d["debloque"], POSTE, lien=d["lien"],
                                         cout=d["cout"] or "0 €", urgent=d["urgent"])
            ouvertes.append(numero)
        except Exception as e:
            print(f"Guichet : {d['titre']} non écrite ({type(e).__name__}: {e})")
    fermees = fermer_demandes(passage.get("fermer", []))
    try:
        telegram.envoyer(message_jules(passage, passage.get("message_jules", ""), verdict))
    except Exception as e:
        print(f"Telegram : {type(e).__name__}: {e}")
    resultat = "ok" if not passage.get("erreur") else f"echec : {passage['erreur']}"[:200]
    registre.ajouter("couts", [{"debut": passage["debut"], "agent": POSTE, "duree_s": duree_s(passage),
                                "jetons_claude": passage["jetons"], "dollars_equiv": passage["cout_usd"],
                                "appels_gratuits": 0, "resultat": resultat}])
    lancer.noter_journal(POSTE, {"date": passage["fin"], "quoi": POSTE, "resultat": "ok" if not passage.get("erreur")
                                 else "echec", "cout_usd": passage["cout_usd"], "arret": passage.get("arret"),
                                 "gardes": len(passage.get("gardes", [])),
                                 "retires": len(passage.get("code_retire", [])), "studio": passage.get("studio"),
                                 "demandes": ouvertes, "fermees": fermees, "juge": (verdict or {}).get("note"),
                                 "bloquant": passage.get("erreur")})


def publier(paquet):
    paquet = Path(paquet)
    try:
        remis = appliquer(RACINE, paquet / "agence.patch", protege)
    except RuntimeError as e:
        print(f"::error::{e}")
        telegram.envoyer(f"Pilote : la séance n'a pas pu être publiée ({e}). Rien n'a été gardé.")
        return 1
    if not PASSAGE.exists():
        print("::error::passage.json absent du paquet")
        return 1
    passage = json.loads(PASSAGE.read_text(encoding="utf-8"))
    passage["proteges_retires"] = sorted(set(passage.get("proteges_retires", [])) | set(remis))
    verdict = None
    try:
        from agence import juge
        verdict = juge.juger(passage, paquet / "agence.patch")
    except Exception as e:     # le juge conseille, il ne bloque jamais la publication
        print(f"Juge : {type(e).__name__}: {e}")
    noter(passage, verdict)
    passage["juge"] = (verdict or {}).get("note")
    PASSAGE.write_text(json.dumps(passage, ensure_ascii=False, indent=1), encoding="utf-8")
    _sortie_github(relancer="oui" if relancer(passage) else "non")
    return 0


def studio():
    """Dans le job de publication, après le patch du studio : remet ce qui pousse ou publie le studio."""
    remis = [c for c in changements(STUDIO) if _sous(c, STUDIO_PROTEGES)]
    defaire(STUDIO, remis)
    if remis:
        print(f"Studio : non gardés (protégés) : {', '.join(remis)}")
    return 0


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "seance":
        sys.exit(seance())
    if action == "trier":
        sys.exit(trier())
    if action == "publier" and len(sys.argv) == 3:
        sys.exit(publier(sys.argv[2]))
    if action == "studio":
        sys.exit(studio())
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
