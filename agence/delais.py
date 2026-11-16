"""Délais des besoins : « Décider vite » (MISSION.md) appliqué par le code, sans modèle.

    python -m agence.lancer delais partir   au réveil : fait partir en essai ce dont le délai de 48 h est dépassé
    python -m agence.delais                 montre les départs possibles et la mesure des délais (ne change rien)

1. Départ en essai. Un besoin écrit depuis plus de 48 h (besoins.DELAI_H) n'attend plus d'analyse ni la séance du
   dimanche : sa première option gratuite et sans compte (voie `essai` du catalogue, classe 1) part chez
   l'Ingénierie par `catalogue.retenir`, au nom du poste qui a le besoin. Une option avec compte (guichet) ou
   payante (capital) ne part jamais d'ici : elle reste à la Direction et à Jules. Un seul départ par passage, et
   pas de nouveau départ pour un besoin tant que 48 h ne sont pas passées depuis le précédent.
2. Mesure. Le temps entre un besoin écrit et sa mise en service (le besoin fermé comme comblé), contre sa cible :
   72 h en classe 1, une semaine en classe 2. Lue par le Chef des opérations (rapport du dimanche) et par le bilan
   du lundi, qui ne citent que ce qui dérape.
"""
import os
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from agence import besoins, catalogue, mesures, registre

CIBLE_H = {1: 72, 2: 168}     # MISSION.md, « Le délai se mesure » : 72 h en classe 1, une semaine en classe 2
DEPARTS_MAX = 3               # par passage : chaque départ est un lancement de l'Ingénierie, dans son budget
JOURS_MESURE = 28


def _heures(debut, fin):
    return round((fin - debut).total_seconds() / 3600)


def a_faire_partir(maintenant):
    """[(besoin, candidat)] : pour chaque besoin au délai dépassé, sa première option de voie essai pas encore
    retenue, relue dans le registre des candidats. Le plus ancien besoin d'abord."""
    candidats = {c["lien"]: c for c in catalogue.candidats_ouverts(maintenant)}
    derniers = {}
    for l in registre.lire_jsonl(catalogue.FICHIER):
        if l.get("besoin"):
            derniers[l["besoin"]] = mesures.quand(l["date"])
    resultat = []
    for b in besoins.dossier(maintenant):
        dernier = derniers.get(b["id"])
        if not b["delai_depasse"] or (dernier and maintenant - dernier < timedelta(hours=besoins.DELAI_H)):
            continue
        for o in b["options"]:
            c = candidats.get(catalogue.normaliser(o.get("lien")))
            if o["voie"] == catalogue.ESSAI and not o.get("deja_retenu") and c:
                resultat.append((b, c))
                break
    return resultat


def partir(maintenant, retenir=None):
    """Fait partir en essai ce qui doit l'être. Renvoie (faits, refus), en phrases."""
    faits, refus = [], []
    for b, c in a_faire_partir(maintenant)[:DEPARTS_MAX]:
        raison = (f"Le besoin {b['id']} ({b['besoin'][:200]}) est écrit depuis {b['age_h']} h, plus que son délai de "
                  f"{besoins.DELAI_H} h : son option gratuite la plus simple part en essai sans attendre (MISSION.md, "
                  f"« Pas de boucle d'analyse »).")
        try:
            _, numero = (retenir or catalogue.retenir)(c, b["par"], raison)
        except (subprocess.CalledProcessError, OSError, ValueError) as e:
            refus.append(f"{c.get('nom')} pour {b['id']} : {str(getattr(e, 'stderr', '') or e)[-200:]}")
            continue
        if numero is not None or os.environ.get("AGENCE_ESSAI") != "1":
            registre.decider(b["par"], f"départ en essai au bout de {besoins.DELAI_H} h : {c.get('nom')} pour le besoin "
                             f"{b['id']}" + (f" (issue #{numero})" if numero else ""), raison[:600])
        faits.append(f"{str(c.get('nom'))[:60]} part en essai pour {b['id']}")
    return faits, refus


def mesure(maintenant, jours=JOURS_MESURE):
    """Le délai besoin → mise en service, besoin par besoin, contre sa cible. Classe 1 (72 h) tant que rien ne dit
    le contraire (« dans le doute, la classe la plus basse ») ; classe 2 (une semaine) quand la voie retenue passe
    par un compte ou de l'argent."""
    voies = {}
    for l in registre.lire_jsonl(catalogue.FICHIER):
        if l.get("besoin"):
            voies[l["besoin"]] = l["voie"]
    depuis, lignes = maintenant - timedelta(days=jours), []
    for b in besoins.etat().values():
        debut, fin = mesures.quand(b["depuis"]), mesures.quand(b["date"])
        classe = 1 if voies.get(b["id"], catalogue.ESSAI) == catalogue.ESSAI else 2
        ligne = {"id": b["id"], "par": b["par"], "classe": classe, "cible_h": CIBLE_H[classe], "voie": voies.get(b["id"])}
        if b["etat"] == "ouvert":
            ligne |= {"etat": "ouvert", "delai_h": _heures(debut, maintenant)}
        elif fin >= depuis and str(b.get("raison", "")).startswith("comblé"):
            ligne |= {"etat": "en service", "delai_h": _heures(debut, fin)}
        else:
            continue   # fermé sans mise en service (abandonné, refusé) ou trop ancien : hors de la mesure
        ligne["en_retard"] = ligne["delai_h"] > ligne["cible_h"]
        lignes.append(ligne)
    servis = [l["delai_h"] for l in lignes if l["etat"] == "en service"]
    return {"cibles_h": {"classe_1": CIBLE_H[1], "classe_2": CIBLE_H[2]}, "besoins": lignes,
            "en_retard": [l["id"] for l in lignes if l["en_retard"] and l["etat"] == "ouvert"],
            "mis_en_service": len(servis), "delai_median_h": round(statistics.median(servis)) if servis else None}


def phrases_retard(m):
    """Une phrase par besoin ouvert qui a dépassé sa cible, pour le rapport des opérations et le bilan."""
    return [f"besoin {l['id']} ouvert depuis {l['delai_h']} h (cible {l['cible_h']} h)"
            for l in m["besoins"] if l["en_retard"] and l["etat"] == "ouvert"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    maintenant = datetime.now(timezone.utc)
    if "partir" not in sys.argv[1:]:
        for b, c in a_faire_partir(maintenant):
            print(f"Partirait en essai : {c.get('nom')} ({c['lien']}) pour {b['id']}, écrit depuis {b['age_h']} h")
        m = mesure(maintenant)
        print("\n".join(phrases_retard(m)) or "Aucun besoin en retard sur sa cible")
        print(f"Mis en service sur {JOURS_MESURE} jours : {m['mis_en_service']}, délai médian : {m['delai_median_h']} h")
        return
    with registre.seance("delais") as info:
        faits, refus = partir(maintenant)
        retards = phrases_retard(mesure(maintenant))
        for r in refus:
            print(f"REFUS {r}")
        info["resultat"] = (f"ok : {'; '.join(faits) or 'aucun départ en essai'}, {len(retards)} besoin(s) en retard "
                            f"sur leur cible" + (f", {len(refus)} départ(s) refusé(s)" if refus else ""))
        print(info["resultat"])


if __name__ == "__main__":
    main()
