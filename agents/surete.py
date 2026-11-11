"""Sûreté : compteur et garde-fous, à chaque réveil, avant le flux. Script pur, 0 jeton.

Lancement : python -m agence.lancer garde_fous   (ou python -m agents.surete --essai : calcule et affiche, n'agit pas)

1. Compteur : dollars Claude et appels gratuits de la semaine par agent (registre/couts.csv, plus l'atelier de
   chaines-studio si ATELIER_COUTS pointe vers son atelier/couts.csv), minutes GitHub du mois des dépôts privés.
2. Seuils (organisation/seuils.toml) : alerte Telegram, puis pause des agents Claude et question pour reprendre.
3. Sanctions : une vidéo rejetée par YouTube met sa chaîne en pause, avec une question à Jules pour reprendre.
4. Pannes : un même programme en échec plusieurs passages d'affilée, alerte.
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

from agence import lancer, organisation, questions, registre, telegram

DEPOTS_PRIVES = ["sueurhocqjules-droid/agence"]  # chaines-studio aussi, quand le réveil pourra le lire


def seuils():
    with open(organisation.DOSSIER / "seuils.toml", "rb") as f:
        return tomllib.load(f)


def couts_atelier():
    """Séances de l'Auteur dans chaines-studio, au format de couts.csv. Vide si le fichier n'est pas lisible ici."""
    chemin = Path(os.environ.get("ATELIER_COUTS") or Path(__file__).resolve().parents[2] / "chaines-studio" / "atelier" / "couts.csv")
    if not chemin.exists():
        return None
    with open(chemin, newline="", encoding="utf-8") as f:
        return [{"debut": l["date"], "agent": "auteur", "dollars_equiv": l["cout_usd_equivalent"], "appels_gratuits": "0"}
                for l in csv.DictReader(f)]


def compteur(maintenant, couts, atelier, reglages, fin=None):
    """Dépenses de la semaine de `maintenant` (jusqu'à `fin` si donnée) : total, par agent, et % de la limite
    hebdomadaire si l'étalon est connu."""
    debut = lancer.debut_semaine(maintenant)
    par_agent = {}
    for ligne in couts + (atelier or []):
        quand = datetime.fromisoformat(ligne["debut"])
        if quand < debut or (fin and quand >= fin):
            continue
        a = par_agent.setdefault(ligne["agent"], {"dollars": 0.0, "appels": 0})
        a["dollars"] += float(ligne["dollars_equiv"] or 0)
        a["appels"] += int(float(ligne["appels_gratuits"] or 0))
    total = sum(a["dollars"] for a in par_agent.values())
    etalon = reglages["claude"]["dollars_par_pourcent"]
    return {"semaine": debut.date().isoformat(), "par_agent": par_agent, "dollars": total,
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

    def mettre_en_pause(self, cible, raison, question):
        """Pause (si pas déjà en pause) et question à Jules pour reprendre."""
        if lancer.pause_active([cible], registre.lire("pauses")):
            return
        print(f"PAUSE {cible} : {raison}")
        if self.essai:
            return
        registre.pause(cible, "surete", raison)
        try:
            questions.poser(question, f"reprise:{cible}", "rien", par="surete")
        except RuntimeError as e:
            print(f"Question non envoyée : {e}")
            self.ratees += 1


def passage(essai):
    reglages, maintenant, s = seuils(), datetime.now(timezone.utc), Surete(essai)

    c = compteur(maintenant, registre.lire("couts"), couts_atelier(), reglages)
    part = f", {c['pourcent']:.1f} % de ta limite" if c["pourcent"] is not None else ""
    detail = ", ".join(f"{a} {v['dollars']:.2f} $" for a, v in sorted(c["par_agent"].items()) if v["dollars"])
    print(f"Semaine du {c['semaine']} : {c['dollars']:.2f} $ équivalent Claude{part} ({detail or 'aucun'}), "
          f"{c['appels']} appels gratuits" + ("" if c["atelier_lu"] else ", atelier de chaines-studio non lu"))

    cl = reglages["claude"]
    if c["dollars"] >= cl["pause_usd_semaine"]:
        for cible in cl["pause_cibles"]:
            s.mettre_en_pause(cible, f"{c['dollars']:.2f} $ Claude cette semaine, plafond {cl['pause_usd_semaine']} $",
                              f"La semaine a déjà coûté {c['dollars']:.2f} $ équivalent Claude (plafond {cl['pause_usd_semaine']} $). "
                              f"J'ai mis {cible} en pause. Le relancer quand même ?")
    if c["dollars"] >= cl["alerte_usd_semaine"]:
        s.alerter(f"claude:{c['semaine']}", "budget", f"{c['dollars']:.2f} $ équivalent Claude depuis lundi{part} "
                  f"({detail}). Seuil d'alerte : {cl['alerte_usd_semaine']} $, pause à {cl['pause_usd_semaine']} $.")
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
        if s.alerter(f"sanction:{video_id}", "sanction", f"YouTube a rejeté « {titre} » ({video_id}, chaîne {chaine}) : {statut}. "
                     f"La chaîne {chaine} est en pause."):
            s.mettre_en_pause(f"chaine:{chaine}", f"vidéo {video_id} rejetée : {statut}",
                              f"YouTube a rejeté « {titre} » sur la chaîne {chaine} ({statut}). Plus aucun envoi sur cette "
                              f"chaîne d'ici ta réponse. Reprendre les envois ?")

    seuil = reglages["echecs"]["alerte_consecutifs"]
    for quoi, depuis, n in echecs_en_serie(registre.DOSSIER / "journal", seuil):
        s.alerter(f"echec:{quoi}:{depuis}", "panne", f"{quoi} a échoué {n} fois d'affilée depuis le {depuis[:16]} UTC. "
                  f"Rien n'est cassé ailleurs, mais ce programme ne fait plus son travail.")

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
