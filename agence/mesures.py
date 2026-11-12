"""Mesures de l'agence : la liste fermée des chiffres sur lesquels une prédiction peut être jugée.

Chaque mesure se calcule à une date donnée, sur les 7 jours qui la précèdent, à partir du registre.
Une prédiction (décision, changement de consignes, essai de créneaux) nomme l'une d'elles, sa valeur avant
et la valeur attendue : le critique la recalcule à l'échéance et rend son verdict.
"""
import tomllib
from datetime import datetime, timedelta

from agence import organisation, registre, youtube

SEMAINE = timedelta(days=7)
MESURES = {
    "vues_semaine": "vues gagnées sur les 7 derniers jours, toutes chaînes",
    **{f"vues_semaine:{l}": f"vues gagnées sur les 7 derniers jours, chaîne {l}" for l in youtube.CHAINES},
    "jours_de_stock": "jours de sorties programmées d'avance, sur la chaîne la moins fournie",
    **{f"jours_de_stock:{l}": f"jours de sorties programmées d'avance, chaîne {l}" for l in youtube.CHAINES},
    "cout_claude_semaine": "dollars Claude (équivalent API) dépensés sur les 7 derniers jours, atelier compris",
    "interventions_jules": "décisions prises par Jules sur les 7 derniers jours",
}


def quand(texte):
    return datetime.fromisoformat(texte.replace("Z", "+00:00")) if texte else None


def heures_de_sortie():
    """Heures de sortie (Paris) par chaîne, réglées par le Programmateur."""
    with open(organisation.DOSSIER / "creneaux.toml", "rb") as f:
        return {langue: r["heures"] for langue, r in tomllib.load(f).items()}


def charger(atelier=None):
    """Les tables du registre dont les mesures ont besoin. `atelier` : les coûts des séances de l'Auteur (surete.couts_atelier)."""
    return {"stats": registre.lire("stats"), "stock": registre.lire("stock"), "couts": registre.lire("couts"),
            "atelier": atelier or [], "decisions": registre.decisions(), "heures": heures_de_sortie()}


def vues_au_releve(stats, avant_le):
    """Vues de chaque vidéo (chaine, video_id) au dernier relevé strictement avant la date, ou {} s'il n'y en a pas."""
    releve = max((l["releve"] for l in stats if quand(l["releve"]) < avant_le), default=None)
    return {(l["chaine"], l["video_id"]): int(l["vues"]) for l in stats if l["releve"] == releve}


def vues_gagnees(stats, a, chaine=None):
    fin, debut = vues_au_releve(stats, a), vues_au_releve(stats, a - SEMAINE)
    if not fin:
        return None
    return sum(v - debut.get(k, 0) for k, v in fin.items() if chaine in (None, k[0]))


def stock_programme(stock, stats, a):
    """Par chaîne, le nombre de sorties programmées après la date, d'après ce qu'on en savait à cette date.

    Deux sources, une sortie comptée une fois par chaîne et par heure : le stock de l'agence, et le dernier relevé
    YouTube (vidéos pas encore publiques), qui voit aussi celles programmées hors de l'agence.
    """
    etat = {}
    for l in stock:
        if quand(l["maj"]) <= a:
            etat[l["nom"]] = l
    sorties = {(l["chaine"], quand(l["sortie_prevue"])) for l in etat.values() if l["etat"] == "programme"}
    releve = max((l["releve"] for l in stats if quand(l["releve"]) <= a), default=None)
    sorties |= {(l["chaine"], quand(l["sortie"])) for l in stats if l["releve"] == releve and l["statut"] != "public"}
    par_chaine = {langue: 0 for langue in youtube.CHAINES}
    for chaine, sortie in sorties:
        if sortie and sortie > a and chaine in par_chaine:
            par_chaine[chaine] += 1
    return par_chaine


def jours_de_stock(stock, stats, heures, a, chaine=None):
    jours = {langue: n / len(heures[langue]) for langue, n in stock_programme(stock, stats, a).items()}
    return round(jours[chaine] if chaine else min(jours.values()), 1)


def cout_sujet(atelier, seances=4):
    """Coût réel d'un sujet livré (dollars équivalent Claude) depuis la `seances`-ième dernière séance qui a livré,
    séances ratées comprises (elles coûtent sans livrer), ou None tant qu'aucune séance ne note ses sujets."""
    notees = [l for l in atelier if str(l.get("sujets") or "").strip() != ""]
    livrees = [i for i, l in enumerate(notees) if int(float(l["sujets"])) > 0]
    lignes = notees[livrees[-seances]:] if len(livrees) >= seances else notees[livrees[0]:] if livrees else []
    sujets = sum(int(float(l["sujets"])) for l in lignes)
    return round(sum(float(l["dollars_equiv"] or 0) for l in lignes) / sujets, 2) if sujets else None


def capacite(atelier):
    """(sujets par semaine que paie le budget de l'Auteur, coût d'un sujet, budget), capacité None sans mesure du coût.
    Le budget est le claude_usd_semaine de la fiche de l'Auteur, que Jules ajuste selon sa propre consommation."""
    budget = float(organisation.fiches()["auteur"]["budget"]["claude_usd_semaine"])
    cout = cout_sujet(atelier)
    return (int(budget // cout) if cout else None), cout, budget


def valeur(mesure, a, donnees):
    """Valeur de la mesure à la date `a`, ou None si le registre ne permet pas de la calculer."""
    if mesure not in MESURES:
        raise ValueError(f"Mesure inconnue : {mesure!r} (liste fermée : {', '.join(MESURES)})")
    nom, _, chaine = mesure.partition(":")
    if nom == "vues_semaine":
        return vues_gagnees(donnees["stats"], a, chaine or None)
    if nom == "jours_de_stock":
        return jours_de_stock(donnees["stock"], donnees["stats"], donnees["heures"], a, chaine or None)
    if nom == "cout_claude_semaine":
        lignes = donnees["couts"] + donnees["atelier"]
        return round(sum(float(l["dollars_equiv"] or 0) for l in lignes if a - SEMAINE <= quand(l["debut"]) < a), 2)
    if nom == "interventions_jules":
        return sum(1 for d in donnees["decisions"] if d["auteur"] == "jules" and a - SEMAINE <= quand(d["date"]) < a)


def tableau(a, donnees):
    """Toutes les mesures à la date, pour un dossier ou une prédiction."""
    return {m: valeur(m, a, donnees) for m in MESURES}
