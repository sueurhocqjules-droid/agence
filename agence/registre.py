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


def decider(auteur, decision, pourquoi, prediction=None, mesure=None, echeance=None):
    """Note une décision au journal d'audit, avec sa raison.

    Avec une prédiction, sa mesure et son échéance, le critique la jugera sur les vrais chiffres.
    """
    entree = {"date": maintenant(), "auteur": auteur, "decision": decision, "pourquoi": pourquoi,
              "prediction": prediction, "mesure": mesure, "echeance": echeance, "verdict": None}
    with open(DOSSIER / "decisions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")


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
