"""Journal de l'Auteur : une ligne par séance de l'atelier dans registre/journal/auteur.jsonl.

L'Auteur tourne hors du lanceur (atelier.yml, dépôt chaines-studio) et note ses séances dans atelier/couts.csv.
Ce code lit ce fichier et recopie chaque séance au registre, une seule fois (la date de la séance sert de clé).
Il est lancé par `garde_fous` (agents/surete.py), à chaque réveil, avec le même fichier de coûts que le compteur.

Une ligne : date et seance (date de la séance), quoi ("atelier"), sujets (livrés, None si non notés),
cout_usd (équivalent API), reserve_usd, echec (vrai si la séance a coûté sans livrer aucun sujet, None si les
sujets ne sont pas notés) et resultat : "ok", "sans_sujet" ou "inconnu". Le mot « echec » n'est pas écrit dans
`resultat` exprès : la Sûreté y lit les pannes de programmes (echecs_en_serie) et en tirerait une fausse panne.
"""
import csv
import json
import os
from pathlib import Path

from agence import lancer, registre

JOURNAL = "auteur"


def chemin_couts():
    return Path(os.environ.get("ATELIER_COUTS")
                or Path(__file__).resolve().parents[2] / "chaines-studio" / "atelier" / "couts.csv")


def lire_seances(chemin):
    """Séances de couts.csv (liste vide si le fichier n'est pas lisible ici)."""
    if not chemin.exists():
        return []
    with open(chemin, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def ligne_de(seance):
    texte = str(seance.get("sujets") or "").strip()
    sujets = int(float(texte)) if texte else None
    echec = None if sujets is None else sujets == 0
    resultat = "inconnu" if echec is None else ("sans_sujet" if echec else "ok")
    return {"date": seance["date"], "seance": seance["date"], "quoi": "atelier", "sujets": sujets,
            "cout_usd": float(seance.get("cout_usd_equivalent") or 0),
            "reserve_usd": float(seance.get("reserve_usd") or 0), "echec": echec, "resultat": resultat}


def noter_seances(chemin=None):
    """Ajoute au journal les séances pas encore notées. Renvoie les lignes ajoutées."""
    seances = lire_seances(chemin or chemin_couts())
    fichier = registre.DOSSIER / "journal" / f"{JOURNAL}.jsonl"
    deja = set()
    if fichier.exists():
        deja = {json.loads(l).get("seance") for l in fichier.read_text(encoding="utf-8").splitlines() if l.strip()}
    neuves = [ligne_de(s) for s in seances if s.get("date") and s["date"] not in deja]
    for ligne in neuves:
        lancer.noter_journal(JOURNAL, ligne)
    return neuves
