"""Registre commun de l'agence : fichiers CSV et JSONL dans registre/, versionnés par Git.

Chaque agent lit et écrit ici, rien d'autre ne fait foi. Colonnes décrites dans registre/README.md.
"""
import csv
import json
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent.parent / "registre"

COLONNES = {
    "stock": ["nom", "chaine", "sujet", "etat", "sortie_prevue", "video_id", "maj", "note"],
    "stats": ["releve", "chaine", "video_id", "titre", "statut", "sortie", "vues", "likes", "commentaires"],
    "couts": ["debut", "agent", "duree_s", "jetons_claude", "dollars_equiv", "appels_gratuits", "resultat"],
    "pauses": ["date", "cible", "action", "par", "raison"],
    "questions": ["date", "id", "par", "texte", "si_oui", "si_non", "etat", "reponse", "message_id"],
    "alertes": ["date", "cle", "niveau", "message"],
    "diffusions": ["date", "reseau", "chaine", "nom", "etat", "media_id", "note"],
}


def maintenant():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ajouter(table, lignes):
    """Ajoute des lignes (dicts) à registre/<table>.csv, en créant l'en-tête si besoin."""
    chemin = DOSSIER / f"{table}.csv"
    neuf = not chemin.exists() or chemin.stat().st_size == 0
    with open(chemin, "a", newline="", encoding="utf-8") as f:
        ecrivain = csv.DictWriter(f, fieldnames=COLONNES[table], extrasaction="raise",
                                  lineterminator="\n")  # mêmes fins de ligne sur Windows et sur GitHub
        if neuf:
            ecrivain.writeheader()
        ecrivain.writerows(lignes)


def lire(table):
    chemin = DOSSIER / f"{table}.csv"
    if not chemin.exists():
        return []
    with open(chemin, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def lire_jsonl(nom, depuis=None):
    """Lignes de registre/<nom>.jsonl, celles datées depuis `depuis` (datetime) si donné."""
    chemin = DOSSIER / f"{nom}.jsonl"
    if not chemin.exists():
        return []
    lignes = [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]
    return [l for l in lignes if not depuis or datetime.fromisoformat(l["date"]) >= depuis]


def refuses():
    """Liens des outils, services ou concepts refusés (registre/refus.jsonl) : la Recherche ne les repropose pas."""
    return {l["lien"] for l in lire_jsonl("refus")}


def decider(auteur, decision, pourquoi, prediction=None, mesure=None, echeance=None, avant=None, attendu=None,
            changement=None, organisation=None):
    """Note une décision au journal d'audit, avec sa raison, et renvoie son identifiant.

    Avec une mesure (liste fermée de agence/mesures.py), sa valeur avant, la valeur attendue et l'échéance,
    le critique la jugera sur les vrais chiffres. `changement` décrit un changement de consignes ou de réglage
    (poste, fichier, section, ancien, nouveau), que le critique annule s'il n'a rien amélioré. `organisation`
    décrit un changement de poste (action creer, supprimer ou fusionner, postes, nouveau), annulé de la même façon.
    """
    ident = f"{auteur}-{datetime.now(timezone.utc):%Y%m%d%H%M%S%f}"
    entree = {"id": ident, "date": maintenant(), "auteur": auteur, "decision": decision, "pourquoi": pourquoi,
              "prediction": prediction, "mesure": mesure, "echeance": echeance, "avant": avant, "attendu": attendu,
              "verdict": None}
    if changement:
        entree["changement"] = changement
    if organisation:
        entree["organisation"] = organisation
    with open(DOSSIER / "decisions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    return ident


def juger(ident, verdict, valeur, commentaire):
    """Ajoute le verdict du critique sur une décision : une nouvelle ligne, le journal ne se réécrit jamais."""
    if verdict not in ("juste", "fausse", "indeterminee"):
        raise ValueError(verdict)
    with open(DOSSIER / "decisions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "verdict", "id": ident, "date": maintenant(), "verdict": verdict,
                            "valeur": valeur, "commentaire": commentaire}, ensure_ascii=False) + "\n")


def decisions():
    """Les décisions du journal d'audit, chacune avec son verdict s'il a été rendu (dict date, verdict, valeur, commentaire)."""
    chemin = DOSSIER / "decisions.jsonl"
    if not chemin.exists():
        return []
    lignes = [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines() if l.strip()]
    verdicts = {l["id"]: l for l in lignes if l.get("type") == "verdict"}
    resultat = []
    for l in lignes:
        if l.get("type") != "verdict":
            v = verdicts.get(l.get("id"))
            resultat.append({**l, "verdict": {k: v[k] for k in ("date", "verdict", "valeur", "commentaire")} if v else None})
    return resultat


def pause(cible, par, raison, action="pause"):
    """Met en pause (ou relance avec action="reprise") un agent, un script, une équipe par son chef, ou "tout".

    La dernière ligne d'une cible fait foi. Le lanceur refuse tout ce qui est en pause, et la décision est notée.
    """
    if action not in ("pause", "reprise"):
        raise ValueError(action)
    ajouter("pauses", [{"date": maintenant(), "cible": cible, "action": action, "par": par, "raison": raison}])
    decider(par, f"{action} : {cible}", raison)


@contextmanager
def seance(agent):
    """Encadre le travail d'un agent et écrit son coût dans registre/couts.csv, même en cas d'échec.

    L'agent remplit le dict reçu : jetons_claude, dollars_equiv, appels_gratuits, resultat.
    """
    debut, info = time.time(), {"jetons_claude": 0, "dollars_equiv": 0, "appels_gratuits": 0, "resultat": "ok"}
    try:
        yield info
    except BaseException as e:
        info["resultat"] = f"echec : {type(e).__name__}: {e}"[:200]
        raise
    finally:
        ajouter("couts", [{"debut": datetime.fromtimestamp(debut, timezone.utc).isoformat(timespec="seconds"),
                           "agent": agent, "duree_s": round(time.time() - debut), **info}])
