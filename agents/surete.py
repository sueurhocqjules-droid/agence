"""Sûreté : compteur et garde-fous, à chaque réveil, avant le flux. Script pur, 0 jeton.

Lancement : python -m agence.lancer garde_fous   (ou python -m agents.surete --essai : calcule et affiche, n'agit pas)

1. Compteur : dollars Claude et appels gratuits de la semaine par agent (registre/couts.csv, plus l'atelier de
   chaines-studio si ATELIER_COUTS pointe vers son atelier/couts.csv), minutes GitHub du mois des dépôts privés.
2. Seuils (organisation/seuils.toml) : alerte Telegram, puis pause des agents Claude et question pour reprendre.
3. Sanctions : une vidéo rejetée par YouTube met sa chaîne en pause, avec une question à Jules pour reprendre.
4. Pannes : un même programme en échec plusieurs passages d'affilée, alerte.
5. Portée : une chaîne que YouTube ne diffuse presque pas (comparée à ses sœurs sur les mêmes sujets) ou dont les vues
   s'effondrent d'une semaine à l'autre (mesures.signaux_portee), alerte une fois par semaine tant que ça dure.
Une alerte ne part qu'une fois : sa clé est notée dans registre/alertes.csv.
"""
import csv
import json
import math
import os
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from pathlib import Path

from agence import lancer, mesures, organisation, questions, registre, telegram

DEPOTS_PRIVES = ["sueurhocqjules-droid/agence"]  # chaines-studio : la clé de lecture ne donne pas accès à l'API des runs

# Raisons de refus de l'API YouTube (videos.status.rejectionReason), en clair, et si c'est grave pour la chaîne
REFUS = {
    "duplicate": ("c'est un doublon d'une vidéo déjà en ligne", False),
    "length": ("la vidéo est trop longue", False),
    "claim": ("un ayant droit revendique un contenu de la vidéo", True),
    "copyright": ("YouTube y voit une atteinte aux droits d'auteur", True),
    "trademark": ("YouTube y voit une atteinte à une marque", True),
    "termsOfUse": ("YouTube y voit une infraction à ses conditions d'utilisation", True),
    "inappropriate": ("YouTube juge le contenu inapproprié", True),
    "legal": ("une raison légale", True),
    "uploaderAccountClosed": ("le compte de la chaîne est fermé", True),
    "uploaderAccountSuspended": ("le compte de la chaîne est suspendu", True),
}


def seuils():
    with open(organisation.DOSSIER / "seuils.toml", "rb") as f:
        return tomllib.load(f)


def couts_atelier():
    """Séances de l'Auteur dans chaines-studio, au format de couts.csv. Vide si le fichier n'est pas lisible ici."""
    chemin = Path(os.environ.get("ATELIER_COUTS") or Path(__file__).resolve().parents[2] / "chaines-studio" / "atelier" / "couts.csv")
    if not chemin.exists():
        return None
    with open(chemin, newline="", encoding="utf-8") as f:
        return [{"debut": l["date"], "agent": "auteur", "dollars_equiv": l["cout_usd_equivalent"], "appels_gratuits": "0",
                 "fin": l.get("fin") or "", "sujets": l.get("sujets") or "", "reserve_usd": l.get("reserve_usd") or "0"} for l in csv.DictReader(f)]


def journaliser_atelier(atelier, dossier=None):
    """Une ligne par séance de l'atelier dans registre/journal/auteur.jsonl, au format du lanceur (début, fin, état,
    coût en $, sujets livrés). Une séance déjà notée (même début) ne l'est pas deux fois. Renvoie le nombre ajouté."""
    chemin = (dossier or registre.DOSSIER / "journal") / "auteur.jsonl"
    deja = set()
    if chemin.exists():
        deja = {json.loads(l).get("debut") for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()}
    nouvelles = [l for l in atelier or [] if l["debut"] not in deja]
    if nouvelles:
        chemin.parent.mkdir(exist_ok=True)
        with open(chemin, "a", encoding="utf-8") as f:
            for l in nouvelles:
                sujets = int(float(l.get("sujets") or 0))
                f.write(json.dumps({"date": l.get("fin") or l["debut"], "quoi": "atelier", "debut": l["debut"],
                                    "fin": l.get("fin") or l["debut"], "resultat": "ok" if sujets else "vide",
                                    "etat": "livre" if sujets else "rien livre",
                                    "dollars_equiv": float(l["dollars_equiv"] or 0), "sujets": sujets},
                                   ensure_ascii=False) + "\n")
    return len(nouvelles)


def compteur(maintenant, couts, atelier, reglages, fin=None):
    """Dépenses de la semaine de `maintenant` (jusqu'à `fin` si donnée) : total, par agent, et % de la limite
    hebdomadaire si l'étalon est connu. `reserve` : la part des séances payée par une réserve accordée par Jules
    (colonne reserve_usd de l'atelier), comptée dans le total mais pas dans les plafonds."""
    debut = lancer.debut_semaine(maintenant)
    par_agent, reserve = {}, 0.0
    for ligne in couts + (atelier or []):
        quand = datetime.fromisoformat(ligne["debut"])
        if quand < debut or (fin and quand >= fin):
            continue
        a = par_agent.setdefault(ligne["agent"], {"dollars": 0.0, "appels": 0})
        a["dollars"] += float(ligne["dollars_equiv"] or 0)
        a["appels"] += int(float(ligne["appels_gratuits"] or 0))
        reserve += min(float(ligne.get("reserve_usd") or 0), float(ligne["dollars_equiv"] or 0))
    total = sum(a["dollars"] for a in par_agent.values())
    etalon = reglages["claude"]["dollars_par_pourcent"]
    return {"semaine": debut.date().isoformat(), "par_agent": par_agent, "dollars": total, "reserve": reserve,
            "hors_reserve": total - reserve,
            "appels": sum(a["appels"] for a in par_agent.values()),
            "pourcent": total / etalon if etalon else None, "atelier_lu": atelier is not None}


def minutes_github(maintenant):
    """Minutes du mois des dépôts privés (durée des runs, arrondie à la minute). None si l'API n'est pas joignable."""
    total = 0
    for depot in DEPOTS_PRIVES:
        r = subprocess.run(["gh", "api", "-X", "GET", f"repos/{depot}/actions/runs", "--paginate",
                            "-f", f"created=>={maintenant:%Y-%m}-01", "-f", "per_page=100",
                            "--jq", ".workflow_runs[] | [.run_started_at, .updated_at] | @tsv"],
                           capture_output=True, text=True)
        if r.returncode:
            print(f"Minutes GitHub illisibles pour {depot} : {r.stderr.strip()[:200]}")
            return None
        for ligne in r.stdout.splitlines():
            debut, fin = (datetime.fromisoformat(x) for x in ligne.split("\t"))
            total += math.ceil(max((fin - debut).total_seconds(), 1) / 60)
    return total


def sanctions(stats):
    """Vidéos du dernier relevé rejetées par la plateforme : [(chaîne, video_id, titre, statut)]."""
    if not stats:
        return []
    dernier = max(l["releve"] for l in stats)
    return [(l["chaine"], l["video_id"], l["titre"], l["statut"]) for l in stats
            if l["releve"] == dernier and l["statut"].startswith("rejete")]


def echecs_en_serie(dossier, seuil):
    """Programmes dont les `seuil` derniers passages ont échoué : [(programme, date du premier échec de la série, n)]."""
    resultat = []
    for chemin in sorted(dossier.glob("*.jsonl")) if dossier.exists() else []:
        passages = {}
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            if ligne.strip():
                e = json.loads(ligne)
                passages.setdefault(e["quoi"], []).append(e)
        for quoi, liste in passages.items():
            serie = []
            for e in reversed(liste):
                if e["resultat"] != "echec":
                    break
                serie.append(e)
            if len(serie) >= seuil:
                resultat.append((quoi, serie[-1]["date"], len(serie)))
    return resultat


def pauses_de_budget_perimees(cibles, pauses, marque):
    """Cibles encore en pause de budget posée par la Sûreté une semaine passée : le compteur est reparti à zéro."""
    perimees = []
    for cible in cibles:
        pause = lancer.pause_active([cible], pauses)
        if pause and pause["par"] == "surete" and pause["raison"].startswith("budget semaine ") \
                and not pause["raison"].startswith(marque):
            perimees.append(cible)
    return perimees


class Surete:
    def __init__(self, essai):
        self.essai, self.envoyees, self.ratees = essai, 0, 0
        self.deja = {l["cle"] for l in registre.lire("alertes")}

    def alerter(self, cle, niveau, message):
        if cle in self.deja:
            return False
        print(f"ALERTE [{niveau}] {message}")
        if self.essai:
            return True
        try:
            telegram.envoyer(f"Alerte sûreté ({niveau})\n\n{message}")
        except RuntimeError as e:
            print(f"Alerte non envoyée, retentée au prochain réveil : {e}")
            self.ratees += 1
            return False
        registre.ajouter("alertes", [{"date": registre.maintenant(), "cle": cle, "niveau": niveau, "message": message}])
        registre.decider("surete", f"alerte : {cle}", message)
        self.deja.add(cle)
        self.envoyees += 1
        return True

    def mettre_en_pause(self, cible, raison, question, pourquoi, conseil):
        """Pause (si pas déjà en pause) et question à Jules pour reprendre, avec ce qui l'aide à trancher."""
        if lancer.pause_active([cible], registre.lire("pauses")):
            return
        print(f"PAUSE {cible} : {raison}")
        if self.essai:
            print(questions.message(question, pourquoi, f"reprise:{cible}", "rien", "surete", conseil))
            return
        registre.pause(cible, "surete", raison)
        try:
            questions.poser(question, f"reprise:{cible}", "rien", par="surete", pourquoi=pourquoi, conseil=conseil)
        except RuntimeError as e:
            print(f"Question non envoyée : {e}")
            self.ratees += 1


def alerter_portee(s, stats, maintenant):
    """Une alerte par chaîne mal diffusée et par semaine, tant que ça dure ; la suite dit qui s'en occupe."""
    semaine = f"{lancer.debut_semaine(maintenant):%Y-%m-%d}"
    for p in mesures.signaux_portee(stats, maintenant):
        suite = ("La Direction te propose ses solutions dans le mail de lundi, et te demande de trancher si c'est une "
                 "refonte ou une fermeture de la chaîne." if p["semaines"] >= mesures.SEMAINES_AVANT_JULES else
                 "La Direction cherche la cause et décide des remèdes dimanche. Rien à faire pour l'instant.")
        s.alerter(f"portee:{p['chaine']}:{p['signal']}:{semaine}", "diffusion",
                  f"{p['texte'][0].upper() + p['texte'][1:]}. {suite}")


def passage(essai):
    reglages, maintenant, s = seuils(), datetime.now(timezone.utc), Surete(essai)

    atelier = couts_atelier()
    if not essai and (ajoutees := journaliser_atelier(atelier)):
        print(f"Journal de l'Auteur : {ajoutees} séance(s) de l'atelier notée(s)")
    c = compteur(maintenant, registre.lire("couts"), atelier, reglages)
    part = f", {c['pourcent']:.1f} % de ta limite" if c["pourcent"] is not None else ""
    detail = ", ".join(f"{a} {v['dollars']:.2f} $" for a, v in sorted(c["par_agent"].items()) if v["dollars"])
    print(f"Semaine du {c['semaine']} : {c['dollars']:.2f} $ équivalent Claude{part} ({detail or 'aucun'}), "
          f"{c['appels']} appels gratuits" + (f", dont {c['reserve']:.2f} $ de réserve accordée par Jules" if c["reserve"] else "")
          + ("" if c["atelier_lu"] else ", atelier de chaines-studio non lu"))

    cl = reglages["claude"]
    marque = f"budget semaine {c['semaine']}"
    for cible in pauses_de_budget_perimees(cl["pause_cibles"], registre.lire("pauses"), marque):
        print(f"REPRISE {cible} : nouvelle semaine")
        if not essai:
            registre.pause(cible, "surete", f"nouvelle semaine ({c['semaine']}) : le compteur repart à zéro", action="reprise")
            questions.clore(f"reprise:{cible}", f"nouvelle semaine, {questions.decrire(cible)} a repris tout seul.")
    if c["hors_reserve"] >= cl["pause_usd_semaine"]:
        for cible in cl["pause_cibles"]:
            s.mettre_en_pause(
                cible, f"{marque} : {c['dollars']:.2f} $ Claude, plafond {cl['pause_usd_semaine']} $",
                f"Je relance {questions.decrire(cible)} malgré le plafond de la semaine ?",
                f"depuis lundi, l'agence a dépensé {c['dollars']:.2f} $ équivalent Claude ({detail}). J'arrête à "
                f"{cl['pause_usd_semaine']} $ pour rester sous 20 % de ta limite hebdomadaire, et il n'y a pas que les "
                f"chaînes qui s'en servent. Donc j'ai mis en pause {questions.decrire(cible)}, le seul à consommer Claude. "
                f"Les vidéos déjà rendues continuent de sortir.",
                "Oui si tu acceptes de dépasser cette semaine (par exemple si tu n'as pas besoin de Claude pour autre chose). "
                "Non si tu préfères garder ta marge : la pause se lève toute seule lundi, quand le compteur repart à zéro.")
    if c["hors_reserve"] >= cl["alerte_usd_semaine"]:
        s.alerter(f"claude:{c['semaine']}", "budget", f"{c['dollars']:.2f} $ équivalent Claude depuis lundi{part} "
                  f"({detail}). Je te préviens à {cl['alerte_usd_semaine']} $, j'arrête l'atelier à {cl['pause_usd_semaine']} $. "
                  f"Rien à faire pour l'instant.")
    if c["pourcent"] is not None and c["pourcent"] >= cl["limite_pourcent"]:
        s.alerter(f"limite:{c['semaine']}", "budget", f"L'agence a passé {cl['limite_pourcent']} % de ta limite "
                  f"hebdomadaire ({c['pourcent']:.1f} %).")

    minutes = minutes_github(maintenant)
    if minutes is not None:
        print(f"GitHub : {minutes} minutes ce mois sur les dépôts privés")
        if minutes >= reglages["github"]["alerte_minutes_mois"]:
            s.alerter(f"github:{maintenant:%Y-%m}", "quota", f"{minutes} minutes GitHub ce mois sur les dépôts privés, "
                      f"sur 2 000 gratuites. Au-delà, les réveils s'arrêtent jusqu'au mois suivant.")

    for chaine, video_id, titre, statut in sanctions(registre.lire("stats")):
        code = statut.partition(":")[2]
        raison, grave = REFUS.get(code, (f"raison donnée par YouTube : « {code or 'aucune'} »", True))
        cible = f"chaine:{chaine}"
        if s.alerter(f"sanction:{video_id}", "sanction", f"YouTube a refusé « {titre} » (https://youtu.be/{video_id}) : {raison}. "
                     f"J'arrête les envois sur cette chaîne, une question suit."):
            s.mettre_en_pause(
                cible, f"vidéo {video_id} refusée : {statut}",
                f"Je reprends {questions.decrire(cible)} ?",
                f"YouTube a refusé la vidéo « {titre} » (https://youtu.be/{video_id}) : {raison}. J'ai arrêté les envois "
                f"sur cette chaîne, parce qu'un deuxième refus peut valoir un avertissement à la chaîne entière, et trois "
                f"avertissements la font fermer. Les autres chaînes continuent.",
                "Ce refus est sans gravité pour la chaîne (souvent une erreur de fichier ou un doublon) : Oui, sans risque."
                if not grave else
                "Regarde d'abord la vidéo dans YouTube Studio pour comprendre ce qui coince. Tant que la cause n'est pas "
                "corrigée (dis-le-moi à ta prochaine session), mieux vaut Non : la chaîne reste en pause jusqu'à ce que "
                "tu me demandes de la relancer.")

    alerter_portee(s, registre.lire("stats"), maintenant)

    seuil = reglages["echecs"]["alerte_consecutifs"]
    for quoi, depuis, n in echecs_en_serie(registre.DOSSIER / "journal", seuil):
        description = organisation.scripts().get(quoi, {}).get("description", quoi)
        s.alerter(f"echec:{quoi}:{depuis}", "panne", f"{description[0].upper() + description[1:]} ({quoi}) a échoué {n} fois "
                  f"d'affilée depuis le {depuis[:16]} UTC. Le reste de l'agence tourne, mais ce travail-là n'est plus fait. "
                  f"Rien à faire sur ton téléphone : dis-le à Claude à ta prochaine session, la cause est dans le journal.")

    return f"ok : {c['dollars']:.2f} $ cette semaine, {s.envoyees} alerte(s) envoyée(s)", s.ratees


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--essai" in sys.argv:
        print(passage(essai=True)[0])
        return
    with registre.seance("garde_fous") as info:
        info["resultat"], ratees = passage(essai=False)
        print(info["resultat"])
    if ratees:
        sys.exit(1)  # Telegram injoignable : le réveil passe au rouge, l'alerte repart au suivant


if __name__ == "__main__":
    main()
