"""Mesures de l'agence : la liste fermée des chiffres sur lesquels une prédiction peut être jugée.

Chaque mesure se calcule à une date donnée, sur les 7 jours qui la précèdent, à partir du registre.
Une prédiction (décision, changement de consignes, essai de créneaux) nomme l'une d'elles, sa valeur avant
et la valeur attendue : le critique la recalcule à l'échéance et rend son verdict.
"""
import statistics
import tomllib
from datetime import datetime, timedelta

from agence import organisation, registre, youtube

SEMAINE = timedelta(days=7)
RECUL = timedelta(days=2)     # une vidéo plus jeune n'a pas encore reçu sa diffusion
PART_MIN_SOEURS = 0.02        # panne : sous 2 % des vues de la meilleure chaîne sœur, sur les mêmes sorties
                              # (13/11 : es non diffusée à 0,04 %, pt diffusée normalement à 7,8 % de en)
SOEUR_MIN = 200               # ... si cette sœur en a au moins autant (sinon tout le monde est bas, rien à comparer)
CHUTE_MAX = 0.2               # chute : médiane sous 20 % de celle de la semaine d'avant
CHUTE_BASE_MIN = 20           # ... si la semaine d'avant valait au moins 20 vues par vidéo
SEMAINES_AVANT_JULES = 2      # à partir de là, la Direction propose ses solutions à Jules
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
    """Heures de sortie (Paris) par chaîne, réglées par le Pilote. Fichier ou chaîne illisible : aucune heure (la
    chaîne ne reçoit rien, les autres continuent ; agents/flux.py borne et filtre les heures)."""
    try:
        with open(organisation.DOSSIER / "creneaux.toml", "rb") as f:
            reglage = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"creneaux.toml illisible ({type(e).__name__}) : aucune sortie programmée")
        return {}
    return {langue: r["heures"] for langue, r in reglage.items()
            if isinstance(r, dict) and isinstance(r.get("heures"), list)}


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


def portee(stats, a):
    """Par chaîne, la diffusion des vidéos sorties dans les 7 jours qui s'arrêtent 2 jours avant `a`, au dernier relevé
    avant `a`. Chaque sujet sort sur toutes les chaînes : les totaux se comparent entre chaînes sœurs.
    panne : moins de 2 % des vues de la meilleure sœur (qui en a au moins 200), sur au moins 3 vidéos.
    chute : médiane sous 20 % de celle de la semaine d'avant. La médiane ignore une vidéo virale isolée."""
    releve = max((l["releve"] for l in stats if quand(l["releve"]) < a), default=None)
    if not releve:
        return {}
    fin = a - RECUL

    def vues(chaine, debut, jusqu_a):
        return [int(l["vues"]) for l in stats if l["releve"] == releve and l["chaine"] == chaine
                and l["statut"] == "public" and l["sortie"] and debut <= quand(l["sortie"]) < jusqu_a]

    res = {}
    for c in youtube.CHAINES:
        v, avant = vues(c, fin - SEMAINE, fin), vues(c, fin - 2 * SEMAINE, fin - SEMAINE)
        res[c] = {"videos": len(v), "vues": sum(v), "mediane": statistics.median(v) if v else None,
                  "mediane_semaine_avant": statistics.median(avant) if avant else None}
    for c, r in res.items():
        soeur = max((x["vues"] for k, x in res.items() if k != c), default=0)
        r["meilleure_soeur"] = soeur
        r["panne"] = r["videos"] >= 3 and soeur >= SOEUR_MIN and r["vues"] < PART_MIN_SOEURS * soeur
        m0 = r["mediane_semaine_avant"]
        r["chute"] = (r["videos"] >= 3 and m0 is not None and m0 >= CHUTE_BASE_MIN
                      and r["mediane"] < CHUTE_MAX * m0)
    return res


def semaines_de_suite(stats, a, chaine, signal, maximum=8):
    """Nombre de semaines d'affilée, en remontant depuis `a`, où le signal (panne ou chute) est levé sur la chaîne."""
    n = 0
    while n < maximum and portee(stats, a - n * SEMAINE).get(chaine, {}).get(signal):
        n += 1
    return n


def signaux_portee(stats, a):
    """Les chaînes en panne ou en chute à la date : chaîne, signal, semaines d'affilée, et une phrase pour Jules."""
    signaux = []
    for c, r in portee(stats, a).items():
        for signal in ("panne", "chute"):
            if not r[signal]:
                continue
            n = semaines_de_suite(stats, a, c, signal)
            if signal == "panne":
                p = r["vues"] / r["meilleure_soeur"] * 100
                part = "moins de 0,1 %" if p < 0.1 else f"{p:.1f} %".replace(".", ",")
                soeur = f"{r['meilleure_soeur']:,}".replace(",", " ")
                texte = (f"chaîne {c} : {r['vues']} vues sur ses {r['videos']} vidéos sorties dans la semaine, contre "
                         f"{soeur} pour la meilleure chaîne sœur sur les mêmes sujets ({part}). "
                         f"YouTube ne la diffuse presque pas")
            else:
                texte = (f"chaîne {c} : {r['mediane']:g} vues par vidéo en médiane sur la semaine, contre "
                         f"{r['mediane_semaine_avant']:g} la semaine d'avant")
            signaux.append({"chaine": c, "signal": signal, "semaines": n,
                            "texte": f"{texte}, {n} semaine{'s' if n > 1 else ''} d'affilée"})
    return signaux


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
    jours = {langue: n / max(1, len(heures.get(langue) or [])) for langue, n in stock_programme(stock, stats, a).items()}
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
