"""Analyste des investissements (étape 11) : ce que rapporterait chaque dépense possible, avant de la faire.

Lancement : python -m agence.lancer analyste   (--essai : calcule et affiche, n'écrit rien)
            python -m agence.lancer prevu_realise   (écart prévu / réalisé des achats faits, à 4 et 8 semaines)

Script `simulation`, Python seul, sans modèle, 0 jeton. Méthode (fiche organisation/postes/analyste.md) :
- Modèle par cohortes sur le vrai registre : sujets par semaine (le moins élevé du budget de l'Auteur et des créneaux),
  3 vidéos par sujet, vues de la première semaine d'une vidéo, puis chaque semaine une part r des vues de la semaine
  d'avant (courbe des vues par âge), abonnés proportionnels aux vues, revenu pub dès que le palier partenaire de
  YouTube est atteint (seuils du Guetteur), RPM des Shorts en hypothèse tant qu'il n'y a pas de revenu.
- Cas de référence « ne rien acheter » toujours présent. Chaque amélioration payante (registre/ameliorations.jsonl,
  fiches du Chercheur d'outils en champs fermés), les paires et le tout sont simulés, jamais additionnés.
- 1 000 tirages, mêmes tirages pour tous les cas (l'écart vient de l'achat, pas du hasard). p10 / p50 / p90.
- Gain d'un vendeur : annoncé = optimiste, médiane = moitié, pessimiste = zéro (tirage uniforme entre 0 et l'annonce).
- Paliers 10, 20, 50, 100, 500 par mois et par poche : meilleure combinaison payable à ce palier, gain marginal
  sur le palier d'en dessous, montant qui suffit (dernier palier dont le gain marginal est au moins 1).
- Deux propositions séparées, € de la poche de Jules et $ de sa limite Claude, jamais additionnées.
Sorties : registre/business-cases.jsonl (une ligne par cas) et registre/tableau-investissements.csv.
"""
import csv
import itertools
import json
import random
import re
import sys
from datetime import date, datetime, timedelta, timezone

from agence import mesures, organisation, registre, youtube
from agents import guetteur, surete

AMELIORATIONS = registre.DOSSIER / "ameliorations.jsonl"
CASES = registre.DOSSIER / "business-cases.jsonl"
TABLEAU = registre.DOSSIER / "tableau-investissements.csv"
INVESTISSEMENTS = registre.DOSSIER / "investissements.jsonl"

MESURES_GAIN = ["cout_par_sujet", "sujets_semaine", "vues", "pourcent_limite", "jours_stock"]
UNITES = {"cout_par_sujet": ["%"], "sujets_semaine": ["%"], "vues": ["%"], "pourcent_limite": ["%"],
          "jours_stock": ["jours"]}
POCHES = {"eur": "EUR", "claude_usd": "USD"}
CHAMPS = {"date", "id", "poste", "lien", "source_gain", "prix", "devise", "periode", "poche", "mesure",
          "gain_annonce", "unite"}
PALIERS = [10, 20, 50, 100, 500]
TIRAGES, SEMAINES, MOIS = 1000, 26, 6
SEMAINES_PAR_MOIS = 52 / 12
VIDEOS_PAR_SUJET = len(youtube.CHAINES)
# Hypothèses écrites, à remplacer par des mesures dès qu'elles existent
EUR_PAR_USD = 0.86                 # change fixe, pour comparer un coût en $ à un gain en €
RPM_EUR = (0.02, 0.10)             # € pour 1 000 vues de Shorts monétisés (aucun revenu mesuré)
RETENUE = (0.10, 0.50)             # part des vues d'une semaine qui revient la semaine suivante
PANNE = (0.02, 0.15)               # chance qu'une semaine ne publie rien, sauf 7 jours de stock d'avance
OBJECTIF_EUR_MOIS = 50


def palier_partenaire(jour):
    p = next(p for p in guetteur.paliers_du_jour(jour) if p["id"] == "yt_partenaire")
    return p["criteres"]["vues_shorts_90j"], p["criteres"]["abonnes"]


# --- Etat actuel, lu dans le registre ---

def etat_actuel(stats, atelier, heures, seuils, stock_jours, maintenant):
    """Le point de départ de toute simulation. `peu_de_donnees` élargit les fourchettes."""
    dernier = max((l["releve"] for l in stats), default=None)
    actuelles = [l for l in stats if l["releve"] == dernier and l["statut"] == "public"]
    ages = [(maintenant - mesures.quand(l["sortie"])).days for l in actuelles if mesures.quand(l["sortie"])]
    jeunes = [int(l["vues"]) for l in actuelles if mesures.quand(l["sortie"])
              and (maintenant - mesures.quand(l["sortie"])).days <= 7]
    vues_s1 = sum(jeunes) / len(jeunes) if jeunes else 100.0
    _, cout, budget = mesures.capacite(atelier)
    cout = cout or 3.0
    creneaux = min(7 * len(h) for h in heures.values()) if heures else 7
    abonnes = sum((l["criteres"][0]["valeur"] or 0) for l in (seuils or {}).get("paliers", [])
                  if l["palier"] == "yt_fans" and l["criteres"][0]["critere"] == "abonnes")
    vues_total = sum(int(l["vues"]) for l in actuelles)
    semaines_donnees = len({l["releve"][:10] for l in stats}) / 7
    return {"vues_s1": round(vues_s1, 1), "cout_sujet": cout, "budget_semaine": budget, "creneaux_sujets": creneaux,
            "abonnes": abonnes, "abonnes_par_vue": (abonnes / vues_total) if vues_total else 0.001,
            "vues_catalogue": vues_total, "jours_stock": stock_jours or 0, "age_max": max(ages, default=0),
            "peu_de_donnees": semaines_donnees < 4, "debut": maintenant.date()}


# --- Tirages et simulation ---

def tirages(base, ids, n=TIRAGES, graine=12):
    """Les mêmes tirages pour tous les cas : hasard du monde et part du gain annoncé obtenue par chaque amélioration."""
    rng = random.Random(graine)
    sigma = 1.0 if base["peu_de_donnees"] else 0.6
    resultat = []
    for _ in range(n):
        resultat.append({"vues_s1": base["vues_s1"] * rng.lognormvariate(-sigma ** 2 / 2, sigma),
                         "retenue": rng.uniform(*RETENUE), "rpm": rng.uniform(*RPM_EUR),
                         "pannes": [rng.random() < rng.uniform(*PANNE) for _ in range(SEMAINES)],
                         "part": {i: rng.random() for i in ids}})
    return resultat


def effets(ameliorations, tirage):
    """Effet combiné des améliorations sur chaque mesure, pour un tirage (composé, jamais additionné)."""
    e = {"cout_par_sujet": 1.0, "sujets_semaine": 1.0, "vues": 1.0, "pourcent_limite": 1.0, "jours_stock": 0.0}
    for a in ameliorations:
        g = a["gain_annonce"] * tirage["part"][a["id"]]   # uniforme entre 0 (pessimiste) et l'annonce (optimiste)
        if a["mesure"] == "jours_stock":
            e["jours_stock"] += g
        elif a["mesure"] == "cout_par_sujet":
            e["cout_par_sujet"] *= max(0.05, 1 - g / 100)
        else:
            e[a["mesure"]] *= 1 + g / 100
    return e


def simuler(base, tirage, ameliorations=()):
    """Une trajectoire de SEMAINES semaines. Sujets = min(budget / coût, créneaux) : un gain sur la contrainte qui
    ne bloque pas ne rapporte rien seul, c'est ce qui rend les combinaisons non additives."""
    e = effets(ameliorations, tirage)
    budget = base["budget_semaine"] * e["pourcent_limite"]
    sujets = min(budget / (base["cout_sujet"] * e["cout_par_sujet"]), base["creneaux_sujets"] * e["sujets_semaine"])
    vues_s1 = tirage["vues_s1"] * e["vues"]
    stock_ok = base["jours_stock"] + e["jours_stock"] >= 7
    vues_semaine, vues_total, revenu, semaine_objectif, fenetre = 0.0, 0.0, 0.0, None, []
    abonnes = base["abonnes"]
    for s in range(SEMAINES):
        publiees = 0 if (tirage["pannes"][s] and not stock_ok) else sujets * VIDEOS_PAR_SUJET
        vues_semaine = vues_semaine * tirage["retenue"] + publiees * vues_s1
        vues_total += vues_semaine
        abonnes += vues_semaine * base["abonnes_par_vue"]
        fenetre = (fenetre + [vues_semaine])[-13:]
        seuil_vues, seuil_abonnes = palier_partenaire(base["debut"] + timedelta(weeks=s))
        par_chaine = len(youtube.CHAINES)
        if sum(fenetre) / par_chaine >= seuil_vues and abonnes / par_chaine >= seuil_abonnes:
            gagne = vues_semaine * tirage["rpm"] / 1000
            revenu += gagne
            if semaine_objectif is None and gagne * SEMAINES_PAR_MOIS >= OBJECTIF_EUR_MOIS:
                semaine_objectif = s + 1
    return {"vues": vues_total, "revenu_eur": revenu, "sujets_semaine": sujets,
            "semaine_objectif": semaine_objectif if semaine_objectif is not None else SEMAINES + 1}


def centiles(valeurs):
    v = sorted(valeurs)
    return [round(v[int(q * (len(v) - 1))], 2) for q in (0.1, 0.5, 0.9)]


# --- Coûts ---

def cout_mois(a, base):
    """Coût mensuel dans la monnaie de sa poche. Un prix à l'usage se paie une fois par sujet produit."""
    usages = 1 if a["periode"] == "mois" else base["budget_semaine"] / base["cout_sujet"] * SEMAINES_PAR_MOIS
    prix = a["prix"] * usages
    if a["devise"] != POCHES[a["poche"]]:
        prix = prix * EUR_PAR_USD if a["devise"] == "USD" else prix / EUR_PAR_USD
    return round(prix, 2)


def en_eur(montant, poche):
    return montant if poche == "eur" else montant * EUR_PAR_USD


# --- Cas ---

def cas(base, tirages_, ameliorations, reference, poche):
    """Un business case : la combinaison simulée sur tous les tirages, comparée tirage par tirage à la référence."""
    sorties = [simuler(base, t, ameliorations) for t in tirages_]
    cout = round(sum(cout_mois(a, base) for a in ameliorations), 2)
    gain_eur = [s["revenu_eur"] - r["revenu_eur"] for s, r in zip(sorties, reference)]
    gain_vues = [s["vues"] - r["vues"] for s, r in zip(sorties, reference)]
    cout_6 = en_eur(cout, poche) * MOIS
    p10, p50, p90 = centiles(gain_eur)
    gagne_par_mois = p50 / MOIS
    return {"cas": [a["id"] for a in ameliorations] or ["reference"], "poche": poche, "cout_mois": cout,
            "devise": POCHES[poche] if ameliorations else None,
            "palier": next((p for p in PALIERS if cout <= p), None) if ameliorations else 0,
            "gain_eur_6_mois": [p10, p50, p90], "gain_vues_6_mois": centiles(gain_vues),
            "vues_6_mois": centiles([s["vues"] for s in sorties]),
            "revenu_eur_6_mois": centiles([s["revenu_eur"] for s in sorties]),
            "sujets_semaine": round(sorties[0]["sujets_semaine"], 1),
            "semaine_objectif_p50": centiles([s["semaine_objectif"] for s in sorties])[1],
            "roi_6_mois": round(p50 / cout_6, 2) if cout_6 else None,
            "pessimiste_perd": (p10 - cout_6) < 0 if ameliorations else False,
            "delai_retour_mois": round(en_eur(cout, poche) / gagne_par_mois, 1) if ameliorations and gagne_par_mois > 0 else None}


def paliers(base, tirages_, ameliorations, reference, poche, simules):
    """Par palier : la meilleure combinaison payable (gain médian en vues, puis en €), et son gain marginal
    sur le palier d'en dessous, en € de gain par € (ou $) dépensé."""
    lignes, avant = [], {"palier": 0, "gain": 0.0, "cas": []}
    for p in PALIERS:
        payables = [c for c in simules if c["poche"] == poche and c["cout_mois"] <= p and c["cas"] != ["reference"]]
        meilleur = max(payables, key=lambda c: (c["gain_eur_6_mois"][1], c["gain_vues_6_mois"][1]), default=None)
        gain = meilleur["gain_eur_6_mois"][1] if meilleur else 0.0
        marge = (gain - avant["gain"]) / (en_eur(p - avant["palier"], poche) * MOIS)
        lignes.append({"palier": p, "poche": poche, "cas": meilleur["cas"] if meilleur else [],
                       "gain_eur_6_mois_p50": gain,
                       "gain_vues_6_mois_p50": meilleur["gain_vues_6_mois"][1] if meilleur else 0.0,
                       "gain_marginal": round(marge, 3), "inutile": marge < 1})
        avant = {"palier": p, "gain": gain, "cas": lignes[-1]["cas"]}
    suffit = 0
    for l in lignes:
        if l["gain_marginal"] >= 1:
            suffit = l["palier"]
    return lignes, suffit


def proposition(simules, poche, suffit):
    """La recommandation d'une poche : le meilleur ROI médian, au moins 1, sans perte dans le cas pessimiste."""
    bons = [c for c in simules if c["poche"] == poche and c["cas"] != ["reference"] and c["roi_6_mois"] is not None
            and c["roi_6_mois"] >= 1 and not c["pessimiste_perd"]]
    meilleur = max(bons, key=lambda c: c["roi_6_mois"], default=None)
    return {"poche": poche, "recommande": meilleur["cas"] if meilleur else [], "montant_qui_suffit": suffit,
            "pourquoi": (f"ROI médian {meilleur['roi_6_mois']} à 6 mois" if meilleur else
                         "aucun cas à ROI médian d'au moins 1 sans perte dans le cas pessimiste : ne rien acheter")}


def lire_ameliorations(lignes, postes=None):
    """Les fiches du Chercheur valides, la plus récente par identifiant. Une fiche hors choix fermés, avec un champ
    en plus (texte libre) ou pour un poste qui n'existe pas est ignorée."""
    postes = set(organisation.fiches()) if postes is None else set(postes)
    gardees = {}
    for a in lignes:
        if (set(a) <= CHAMPS and a.get("poste") in postes and str(a.get("lien", "")).startswith("https://")
                and str(a.get("source_gain", "")).startswith("https://")
                and a.get("poche") in POCHES and a.get("mesure") in MESURES_GAIN and a.get("devise") in ("EUR", "USD")
                and a.get("periode") in ("mois", "usage") and isinstance(a.get("prix"), (int, float)) and a["prix"] > 0
                and isinstance(a.get("gain_annonce"), (int, float)) and a["gain_annonce"] > 0
                and a.get("unite") in UNITES[a["mesure"]] and re.fullmatch(r"[a-z0-9_-]{1,40}", str(a.get("id")))):
            gardees[a["id"]] = a
    return list(gardees.values())[-5:]


def analyser(base, ameliorations, n=TIRAGES):
    ids = [a["id"] for a in ameliorations]
    t = tirages(base, ids, n)
    reference = [simuler(base, x) for x in t]
    simules = [cas(base, t, [], reference, "eur")]
    for poche in POCHES:
        miennes = [a for a in ameliorations if a["poche"] == poche]
        combinaisons = [c for k in range(1, len(miennes) + 1) for c in itertools.combinations(miennes, k)]
        for combo in combinaisons:
            c = cas(base, t, list(combo), reference, poche)
            if len(combo) > 1:  # la somme des gains seuls, pour montrer que la combinaison ne l'est pas
                seuls = [s for s in simules if s["poche"] == poche and len(s["cas"]) == 1 and s["cas"][0] in c["cas"]]
                c["somme_des_seuls_vues_p50"] = round(sum(s["gain_vues_6_mois"][1] for s in seuls), 2)
            simules.append(c)
    resultat = {"reference": simules[0], "cas": simules, "paliers": {}, "propositions": {}}
    for poche in POCHES:
        lignes, suffit = paliers(base, t, ameliorations, reference, poche, simules)
        resultat["paliers"][poche] = lignes
        resultat["propositions"][poche] = proposition(simules, poche, suffit)
    return resultat


def ecrire(resultat, base, maintenant):
    date_ = maintenant.isoformat(timespec="seconds")
    with open(CASES, "a", encoding="utf-8", newline="\n") as f:
        for c in resultat["cas"]:
            f.write(json.dumps({"date": date_, "type": "cas", **c}, ensure_ascii=False) + "\n")
        for poche, lignes in resultat["paliers"].items():
            for l in lignes:
                f.write(json.dumps({"date": date_, "type": "palier", **l}, ensure_ascii=False) + "\n")
        for p in resultat["propositions"].values():
            f.write(json.dumps({"date": date_, "type": "proposition", **p}, ensure_ascii=False) + "\n")
        f.write(json.dumps({"date": date_, "type": "hypotheses", "etat": {k: str(v) if isinstance(v, date) else v
                                                                          for k, v in base.items()},
                            "rpm_eur": RPM_EUR, "retenue": RETENUE, "panne": PANNE, "eur_par_usd": EUR_PAR_USD,
                            "tirages": TIRAGES, "semaines": SEMAINES}, ensure_ascii=False) + "\n")
    with open(TABLEAU, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "cas", "poche", "cout_mois", "devise", "palier", "vues_6m_p10", "vues_6m_p50", "vues_6m_p90",
                    "gain_vues_p50", "gain_eur_p10", "gain_eur_p50", "gain_eur_p90", "roi_6_mois", "delai_retour_mois",
                    "pessimiste_perd", "sujets_semaine"])
        for c in resultat["cas"]:
            w.writerow([date_, "+".join(c["cas"]), c["poche"], c["cout_mois"], c["devise"] or "", c["palier"],
                        *c["vues_6_mois"], c["gain_vues_6_mois"][1], *c["gain_eur_6_mois"], c["roi_6_mois"],
                        c["delai_retour_mois"], c["pessimiste_perd"], c["sujets_semaine"]])


def resume(resultat, base):
    r = resultat["reference"]
    n = lambda x: f"{x:,.0f}".replace(",", " ")
    lignes = [f"Référence « ne rien acheter » : {n(r['vues_6_mois'][1])} vues sur 6 mois (p10 {n(r['vues_6_mois'][0])}, "
              f"p90 {n(r['vues_6_mois'][2])}), revenu {r['revenu_eur_6_mois'][1]:.2f} €, "
              f"{r['sujets_semaine']} sujets/semaine"]
    if base["peu_de_donnees"]:
        lignes.append("Peu de données (moins de 4 semaines de relevés) : fourchettes élargies")
    if len(resultat["cas"]) == 1:
        lignes.append("Aucune amélioration payante au registre (registre/ameliorations.jsonl) : cas de référence seul")
    for poche, p in resultat["propositions"].items():
        lignes.append(f"Proposition {POCHES[poche]} : {' + '.join(p['recommande']) or 'rien'} ({p['pourquoi']}), "
                      f"montant qui suffit {p['montant_qui_suffit']} {POCHES[poche]}/mois")
    return lignes


def derniers_cas(lignes=None):
    """Le dernier passage de la simulation, pour le dossier de la Direction et le bilan : propositions par poche,
    paliers, les 10 cas au meilleur ROI, identifiants simulés. None si la simulation n'a jamais tourné."""
    lignes = registre.lire_jsonl(CASES.stem) if lignes is None else lignes
    if not lignes:
        return None
    dernier = max(l["date"] for l in lignes)
    les = [l for l in lignes if l["date"] == dernier]
    cas_ = [l for l in les if l["type"] == "cas"]
    payants = sorted((c for c in cas_ if c["cas"] != ["reference"]), key=lambda c: -(c["roi_6_mois"] or 0))
    return {"date": dernier, "propositions": [l for l in les if l["type"] == "proposition"],
            "reference": next((c for c in cas_ if c["cas"] == ["reference"]), None), "meilleurs_cas": payants[:10],
            "paliers": [l for l in les if l["type"] == "palier"],
            "a_eviter": [c["cas"] for c in payants if c["roi_6_mois"] is not None and c["roi_6_mois"] < 1][:3],
            "ids": sorted({i for c in payants for i in c["cas"]})}


def charger_base(maintenant):
    stats = registre.lire("stats")
    seuils = json.loads(guetteur.SEUILS.read_text(encoding="utf-8")) if guetteur.SEUILS.exists() else {}
    donnees = mesures.charger(surete.couts_atelier())
    try:
        stock = mesures.jours_de_stock(donnees["stock"], stats, donnees["heures"], maintenant)
    except (ValueError, ZeroDivisionError, KeyError):
        stock = 0
    return etat_actuel(stats, donnees["atelier"], donnees["heures"], seuils, stock, maintenant)


# --- Script prevu_realise ---

def prevu_realise(investissements, valeur, maintenant):
    """Pour chaque achat accordé par Jules : la mesure 4 et 8 semaines après l'achat, comparée à sa fourchette prévue
    (prevu = [p10, p50, p90] de la même mesure). `valeur(mesure, date)` lit le registre. Échéance pas encore
    passée : None."""
    resultats = []
    for inv in investissements:
        achat = mesures.quand(inv["date"])
        ligne = {"id": inv["id"], "mesure": inv["mesure"], "prevu": inv["prevu"]}
        for semaines in (4, 8):
            quand = achat + timedelta(weeks=semaines)
            mesure = valeur(inv["mesure"], quand) if quand <= maintenant else None
            ligne[f"s{semaines}"] = None if mesure is None else {
                "mesure": mesure, "dans_fourchette": inv["prevu"][0] <= mesure <= inv["prevu"][2],
                "ecart_median": round(mesure - inv["prevu"][1], 2)}
        resultats.append(ligne)
    return resultats


def ecarts(maintenant=None, investissements=None):
    """(lignes de prevu_realise, phrase de synthèse) sur le vrai registre. Le bilan du lundi s'en sert aussi."""
    maintenant = maintenant or datetime.now(timezone.utc)
    investissements = registre.lire_jsonl(INVESTISSEMENTS.stem) if investissements is None else investissements
    if not investissements:
        return [], "aucun achat accordé par Jules (registre/investissements.jsonl vide) : rien à comparer"
    donnees = mesures.charger(surete.couts_atelier())
    r = prevu_realise(investissements, lambda m, a: mesures.valeur(m, a, donnees), maintenant)
    dans = sum(1 for l in r for s in ("s4", "s8") if l[s] and l[s]["dans_fourchette"])
    jugees = sum(1 for l in r for s in ("s4", "s8") if l[s])
    return r, f"{len(r)} achat(s), {dans} mesure(s) dans la fourchette prévue sur {jugees} jugée(s)"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    essai = "--essai" in sys.argv
    maintenant = datetime.now(timezone.utc)
    base = charger_base(maintenant)
    resultat = analyser(base, lire_ameliorations(registre.lire_jsonl(AMELIORATIONS.stem)))
    lignes = resume(resultat, base)
    if essai:
        print("ESSAI :\n" + "\n".join(lignes))
        return
    with registre.seance("analyste") as info:
        ecrire(resultat, base, maintenant)
        print("\n".join(lignes))
        info["resultat"] = "ok : " + lignes[0][:180]


if __name__ == "__main__":
    main()
