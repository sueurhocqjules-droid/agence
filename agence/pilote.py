"""Pilote : le seul agent qui décide. Une séance Claude Code (web, fichiers, commandes) qui avance vers l'objectif de
organisation/MISSION.md, puis un script qui garde ce qui est sûr et vert.

    python -m agence.pilote seance      séance Claude dans ce dépôt (et chaines-studio/ à côté)
    python -m agence.pilote trier       étape suivante : garde ce qui est sûr et vert, retire le reste
    python -m agence.pilote noter       sur le main à jour : coût et journal de la séance (registre/pilote/passage.json)

Le workflow `.github/workflows/pilote.yml` enchaîne les deux, et pousse ce qui a été gardé.

Règle de deux : la séance lit le web [A] mais n'a aucun secret [B] (seul son propre jeton, illisible par ses
commandes) et n'agit dehors [C] qu'à travers ce script : il retire les fichiers protégés, fait passer les tests et
fait relire tout changement de code par un modèle qui n'est pas Claude avant de le garder. Le code gardé tourne
ensuite avec des clés (flux, stats) : c'est pour ça qu'il est relu.
"""
import json
import os
import shutil
import subprocess
import sys
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
MODELE = "claude-opus-5-5"
TOURS_MAX = 400                                # garde-fou contre une séance qui tourne en rond, pas une limite de travail
DUREE_MAX_S = 150 * 60
OUTILS = "Read,Edit,Write,Glob,Grep,Bash,WebSearch,WebFetch,TodoWrite"
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
    "agence/relecture.py",
    "agence/equipe.py",
    "tests/test_equipe.py",
    "agents/surete.py",
    "tests/test_pilote.py",
)
# Le registre est écrit par les scripts du réveil : la séance n'y écrit que dans registre/pilote/ (son carnet)
REGISTRE, CARNET_REL = "registre/", "registre/pilote/"
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
            elif p.exists():
                p.unlink()


# --- Budget et rythme ------------------------------------------------------------------------------------------

def rythme():
    with open(organisation.DOSSIER / "rythme.toml", "rb") as f:
        return tomllib.load(f).get("pilote", {})


def plafond_seance(maintenant, couts, atelier, reglages, reglage_rythme):
    """(plafond en $ de cette séance, dépensé cette semaine, seuil de pause). Le seul vrai plafond est le budget
    de la semaine (seuils.toml, fixé par Jules) ; usd_max_seance est le partage que le Pilote choisit lui-même."""
    from agents import surete   # import tardif : surete importe ce module par questions → lancer
    depense = surete.compteur(maintenant, couts, atelier, reglages)["dollars"]
    pause = float(reglages["claude"]["pause_usd_semaine"])
    reste = pause - depense
    par_seance = float(reglage_rythme.get("usd_max_seance") or reste)
    return max(0.0, min(reste, par_seance)), depense, pause


# --- Séance ----------------------------------------------------------------------------------------------------

def demandes_ouvertes():
    """Demandes du guichet en attente de Jules, en texte court pour la consigne (GitHub illisible : dit tel quel)."""
    try:
        demandes = guichet.ouvertes()
    except Exception as e:
        return f"illisibles ({type(e).__name__})"
    return "\n".join(f"#{d['numero']} {d['titre']} (depuis le {d['date'][:10]})" for d in demandes) or "aucune"


def consigne(maintenant, plafond, depense, pause, ouvertes="aucune"):
    dernier = PASSAGE.read_text(encoding="utf-8") if PASSAGE.exists() else "aucun (première séance)"
    return f"""Tu es le Pilote de l'agence. Lis d'abord organisation/PILOTE.md (ton mode d'emploi), puis
organisation/MISSION.md, puis ton carnet registre/pilote/carnet.md s'il existe. Ensuite, fais avancer l'agence vers
l'objectif, jusqu'au bout de ce que tu peux faire dans cette séance.

Nous sommes le {maintenant:%Y-%m-%d %H:%M} UTC.
Budget Claude : {depense:.2f} $ dépensés cette semaine (depuis lundi 0 h UTC) sur {pause:.0f} $ au plus.
Cette séance s'arrête d'elle-même à {plafond:.2f} $ ou {DUREE_MAX_S // 60} minutes : garde de quoi écrire ton carnet
et ton rapport avant la fin.

Demandes au guichet qui attendent Jules (ne les redemande pas, ferme celles qui ne servent plus) :
{ouvertes[:3000]}

Ce que le script a fait du résultat de ta séance précédente :
{dernier[:6000]}"""


def seance_claude(texte, plafond, executer=subprocess.run):
    """Lance Claude Code à la racine du dépôt. Renvoie {ok, resume, cout, jetons, tours, erreur}."""
    commande = ["claude", "-p", "--model", MODELE, "--output-format", "json", "--max-turns", str(TOURS_MAX),
                "--max-budget-usd", f"{plafond:.2f}", "--tools", OUTILS, "--allowedTools", OUTILS,
                "--disallowedTools", "Agent,Task", "--permission-mode", "dontAsk", "--strict-mcp-config",
                "--setting-sources", "", "--no-session-persistence", "--add-dir", str(STUDIO)]
    # Claude ne reçoit que son propre jeton, et ses commandes ne le voient pas (environnement nettoyé)
    env = lancer.env_cloisonne(os.environ, {"CLAUDE_CODE_OAUTH_TOKEN"}) | {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB": "1",
                                                                           "PYTHONUTF8": "1"}
    try:
        proc = executer(commande, input=texte, capture_output=True, text=True, encoding="utf-8",
                        timeout=DUREE_MAX_S, cwd=str(RACINE), env=env)
    except subprocess.TimeoutExpired:
        return {"ok": False, "resume": "", "cout": 0.0, "jetons": 0, "tours": None,
                "erreur": f"séance coupée après {DUREE_MAX_S // 60} min (coût non lu)"}
    try:
        sortie = json.loads(proc.stdout)
    except ValueError:
        sortie = {}
    if not isinstance(sortie, dict):
        sortie = {}
    usage = sortie.get("usage") or {}
    jetons = sum(usage.get(k, 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens",
                                             "cache_creation_input_tokens"))
    ok = proc.returncode == 0 and not sortie.get("is_error") and sortie.get("subtype", "success") == "success"
    erreur = None if ok else (f"séance arrêtée ({sortie.get('subtype') or f'code {proc.returncode}'}) : "
                              f"{str(sortie.get('result') or proc.stderr or proc.stdout)[-400:]}")
    return {"ok": ok, "resume": str(sortie.get("result") or ""), "cout": float(sortie.get("total_cost_usd") or 0),
            "jetons": jetons, "tours": sortie.get("num_turns"), "erreur": erreur}


# --- Tri du résultat -------------------------------------------------------------------------------------------

def tests_verts():
    proc = subprocess.run([sys.executable, "-m", "unittest", "discover", "-q", "tests"], cwd=str(RACINE),
                          capture_output=True, text=True, encoding="utf-8")
    return proc.returncode == 0, (proc.stdout + proc.stderr)[-1500:]


def relire_code(chemins):
    """Avis d'un modèle gratuit (pas Claude) sur le diff du code. Renvoie (ok, détail)."""
    from agence import relecture
    diff = _git(RACINE, "diff", "HEAD", "--", *chemins)
    try:
        avis, modele = relecture.relire("Séance du Pilote", diff)
    except Exception as e:   # panne des modèles gratuits : le code n'est pas gardé, la séance suivante réessaie
        return False, f"relecture impossible : {type(e).__name__}: {e}"[:300]
    risques = "; ".join(f"{r.get('fichier')}: {r.get('raison')}" for r in avis.get("risques", []))
    return avis.get("verdict") == "ok", f"{avis.get('verdict')} ({modele}) {risques}"[:600]


def trier_agence():
    """Garde ce qui est sûr : protégés retirés, tests verts, code relu. Renvoie le bilan pour le passage."""
    bilan = {"proteges_retires": [], "code_retire": [], "tests": "non lancés", "relecture": "aucun code"}
    chemins = changements(RACINE)
    proteges = [c for c in chemins if protege(c)]
    if proteges:
        defaire(RACINE, proteges)
        bilan["proteges_retires"] = proteges
    chemins = [c for c in chemins if c not in proteges]
    code = [c for c in chemins if c.endswith(CODE) or c.startswith("tests/")]
    if code:
        ok, detail = tests_verts()
        bilan["tests"] = "verts" if ok else f"rouges, code retiré : {detail}"
        if ok:
            ok, bilan["relecture"] = relire_code(code)
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
    for etape in (["python3", "scripts/tri_atelier.py"], ["npm", "run", "lint"]):
        proc = subprocess.run(etape, cwd=str(STUDIO), capture_output=True, text=True, encoding="utf-8")
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


def demandes_du_rapport():
    """Message à Jules, demandes au guichet et demandes à fermer écrits par la séance (rapport.json), sûrs à envoyer."""
    try:
        rapport = json.loads(RAPPORT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "", [], []
    if not isinstance(rapport, dict):
        return "", [], []
    message = guichet.sans_mention(rapport.get("message_jules"), 1500)
    demandes, fermer = [], []
    for d in (rapport.get("demandes") or [])[:10]:
        if isinstance(d, dict) and d.get("titre") and d.get("quoi"):
            demandes.append({k: guichet.sans_mention(d.get(k), 1500) for k in ("titre", "quoi", "pourquoi", "debloque",
                                                                                 "lien", "cout")}
                            | {"urgent": bool(d.get("urgent"))})
    for f in (rapport.get("fermer") or [])[:20]:
        if isinstance(f, dict) and str(f.get("numero", "")).isdigit():
            fermer.append({"numero": int(f["numero"]), "raison": guichet.sans_mention(f.get("raison") or "obsolète", 500)})
    return message, demandes, fermer


def seance():
    maintenant = datetime.now(timezone.utc)
    pause = lancer.pause_active([POSTE, lancer.TOUT], registre.lire("pauses"))
    if pause:
        print(f"Pilote en pause ({pause['cible']}, par {pause['par']} : {pause['raison']})")
        return 0
    from agents import surete
    plafond, depense, seuil = plafond_seance(maintenant, registre.lire("couts"), surete.couts_atelier(),
                                             surete.seuils(), rythme())
    if plafond < 1:
        print(f"Budget de la semaine atteint : {depense:.2f} $ sur {seuil:.0f} $, pas de séance")
        return 0
    CARNET.mkdir(parents=True, exist_ok=True)
    RAPPORT.unlink(missing_ok=True)
    debut = registre.maintenant()
    s = seance_claude(consigne(maintenant, plafond, depense, seuil, demandes_ouvertes()), plafond)
    message, demandes, fermer = demandes_du_rapport()
    RAPPORT.unlink(missing_ok=True)       # lu une fois : ne repart pas à la séance suivante
    passage = {"debut": debut, "fin": registre.maintenant(), "cout_usd": round(s["cout"], 4), "jetons": s["jetons"],
               "tours": s["tours"], "erreur": s["erreur"], "resume": s["resume"][-3000:],
               "message_jules": message, "demandes": demandes, "fermer": fermer, "trie": False}
    PASSAGE.write_text(json.dumps(passage, ensure_ascii=False, indent=1), encoding="utf-8")
    _sortie_github(faite="oui")
    return 0


def trier():
    """Après la séance, dans une étape à part : seule celle-ci reçoit les clés des modèles gratuits (relecture),
    jamais lisibles par les commandes de Claude."""
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


def message_jules(passage, message):
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


def noter():
    """Sur le main à jour (job de publication, seul écrivain du registre) : coût, journal, demandes au guichet et
    message à Jules, à partir de passage.json."""
    passage = json.loads(PASSAGE.read_text(encoding="utf-8"))
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
        telegram.envoyer(message_jules(passage, passage.get("message_jules", "")))
    except Exception as e:
        print(f"Telegram : {type(e).__name__}: {e}")
    duree = round((datetime.fromisoformat(passage["fin"]) - datetime.fromisoformat(passage["debut"])).total_seconds())
    resultat = "ok" if not passage.get("erreur") else f"echec : {passage['erreur']}"[:200]
    registre.ajouter("couts", [{"debut": passage["debut"], "agent": POSTE, "duree_s": duree,
                                "jetons_claude": passage["jetons"], "dollars_equiv": passage["cout_usd"],
                                "appels_gratuits": 0, "resultat": resultat}])
    lancer.noter_journal(POSTE, {"date": passage["fin"], "quoi": POSTE, "resultat": "ok" if not passage.get("erreur")
                                 else "echec", "cout_usd": passage["cout_usd"],
                                 "gardes": len(passage.get("gardes", [])), "studio": passage.get("studio"),
                                 "demandes": ouvertes, "fermees": fermees, "bloquant": passage.get("erreur")})


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "seance":
        sys.exit(seance())
    if action == "trier":
        sys.exit(trier())
    if action == "noter":
        sys.exit(noter())
    sys.exit(__doc__)


if __name__ == "__main__":
    main()
