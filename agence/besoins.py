"""Boucle des besoins : tout agent écrit ce qui lui manque, en chiffres, et la Recherche le traite en priorité.

    python -m agence.besoins        montre les besoins ouverts et leurs options (ne change rien)

Le circuit (MISSION.md, « Décider vite ») :
1. Un agent appelle `besoins.exprimer(par, cle, besoin, manque, unite, pourquoi)` : une ligne dans
   registre/besoins.jsonl. Exemple, le Programmateur : « 5 sorties par jour demandent 35 sujets par semaine, le
   budget en paie 8 : il manque 27 sujets par semaine ».
2. Le Chercheur d'outils lit les besoins ouverts avant tout le reste et rattache ses trouvailles au besoin
   (champ `besoin` d'un candidat gratuit ou d'une amélioration payante, simulée par l'Analyste).
3. La Direction lit chaque besoin dans son dossier avec 3 options au plus, les gratuites d'abord, chacune avec
   sa voie (agence/catalogue.py) : essai par l'Ingénierie, guichet, ou demande de capital avec son business case.
4. L'agent ferme son besoin quand le manque a disparu (`exprimer` avec un manque nul, ou `clore`).

Le registre ne se réécrit pas : la dernière ligne d'un besoin fait foi, la première de sa période ouverte donne
son âge, que le délai de 48 h compare.
"""
import json
import re
import sys
from datetime import datetime, timezone

from agence import mesures, organisation, registre

FICHIER = "besoins"
DELAI_H = 48          # MISSION.md, « Pas de boucle d'analyse » : un besoin a un délai, 48 h par défaut
OPTIONS_MAX = 3       # ... et au plus 3 options
CHAMPS_OPTION = ("nom", "lien", "pourquoi", "compte_requis", "essai", "economie_usd_semaine")


def _ecrire(ligne):
    with open(registre.DOSSIER / f"{FICHIER}.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def etat(lignes=None):
    """{id: besoin} : la dernière ligne de chaque besoin, avec `depuis` (début de sa période ouverte)."""
    lignes = registre.lire_jsonl(FICHIER) if lignes is None else lignes
    besoins = {}
    for l in lignes:
        avant = besoins.get(l["id"])
        depuis = avant["depuis"] if avant and avant["etat"] == "ouvert" else l["date"]
        besoins[l["id"]] = {**l, "depuis": depuis}
    return besoins


def ouverts(lignes=None):
    """Les besoins ouverts, le plus ancien d'abord."""
    return sorted((b for b in etat(lignes).values() if b["etat"] == "ouvert"), key=lambda b: b["depuis"])


def exprimer(par, cle, besoin, manque, unite, pourquoi, postes=None):
    """Écrit (ou met à jour) le besoin chiffré d'un agent. Renvoie (id, écrit).

    par : un poste qui existe. cle : ce qui manque, en un mot (un besoin par poste et par clé). manque : le nombre
    qui manque, dans `unite` ; nul ou négatif, le besoin ouvert est fermé (« comblé »). Rien n'est écrit si le
    besoin est déjà ouvert avec le même chiffre : le registre ne grossit pas à chaque réveil.
    """
    postes = organisation.fiches() if postes is None else postes
    if par not in postes:
        raise ValueError(f"poste inconnu : {par!r}")
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", str(cle)):
        raise ValueError(f"clé invalide : {cle!r}")
    if isinstance(manque, bool) or not isinstance(manque, (int, float)):
        raise ValueError(f"un besoin se chiffre : {manque!r}")
    if not str(unite).strip() or not str(besoin).strip() or not str(pourquoi).strip():
        raise ValueError("besoin, unité ou raison manquant")
    ident = f"{par}-{cle}"
    actuel = etat().get(ident)
    ouvert = bool(actuel) and actuel["etat"] == "ouvert"
    if manque <= 0:
        if ouvert:
            clore(ident, par, "comblé : il ne manque plus rien")
        return ident, ouvert
    if ouvert and actuel["manque"] == manque:
        return ident, False
    _ecrire({"id": ident, "date": registre.maintenant(), "par": par, "cle": cle, "besoin": str(besoin)[:400],
             "manque": manque, "unite": str(unite)[:60], "pourquoi": str(pourquoi)[:400], "etat": "ouvert"})
    return ident, True


def clore(ident, par, raison):
    """Ferme un besoin ouvert, avec sa raison (comblé, abandonné, refusé). Renvoie vrai s'il l'était."""
    actuel = etat().get(ident)
    if not actuel or actuel["etat"] != "ouvert":
        return False
    _ecrire({**{k: actuel[k] for k in ("id", "par", "cle", "besoin", "manque", "unite", "pourquoi")},
             "date": registre.maintenant(), "etat": "clos", "clos_par": par, "raison": str(raison)[:300]})
    return True


def pour_la_recherche(lignes=None):
    """Ce que la Recherche lit d'un besoin : son identifiant (à recopier), qui, quoi, combien."""
    return [{k: b[k] for k in ("id", "par", "besoin", "manque", "unite", "pourquoi", "depuis")} for b in ouverts(lignes)]


def options(ident, candidats, ameliorations, cas=None, exclus=(), retenus=None):
    """Les options d'un besoin, 3 au plus, les gratuites d'abord (sans compte avant avec compte), puis les payantes
    avec leur business case s'il a été simulé. La plus récente d'abord dans chaque groupe. `exclus` : liens refusés
    ou déjà au catalogue. `retenus` : outils déjà envoyés à l'essai ou au guichet (dit dans l'option)."""
    from agence import catalogue
    retenus = retenus or {}
    gratuites = [{"genre": "gratuit", "voie": catalogue.voie(c), **{k: c.get(k) for k in CHAMPS_OPTION},
                  "deja_retenu": catalogue.normaliser(c.get("lien")) in retenus}
                 for c in reversed(candidats)
                 if c.get("besoin") == ident and catalogue.normaliser(c.get("lien")) not in exclus]
    gratuites.sort(key=lambda o: o["voie"] != catalogue.ESSAI)
    simules = {tuple(c["cas"]): c for c in (cas or {}).get("meilleurs_cas", [])}
    payantes = []
    for a in reversed(ameliorations):
        if a.get("besoin") != ident or any(p["id"] == a["id"] for p in payantes):
            continue
        c = simules.get((a["id"],))
        payantes.append({"genre": "payant", "voie": catalogue.CAPITAL, "id": a["id"], "lien": a["lien"],
                         "prix": a["prix"], "devise": a["devise"], "periode": a["periode"], "poche": a["poche"],
                         "business_case": c and {k: c.get(k) for k in ("cout_mois", "gain_eur_6_mois", "gain_vues_6_mois",
                                                                      "roi_6_mois", "pessimiste_perd")}})
    return (gratuites + payantes)[:OPTIONS_MAX]


def dossier(maintenant=None, cas=None):
    """Les besoins ouverts tels que la Direction les lit : le chiffre, l'âge, le délai, et les options trouvées."""
    from agence import catalogue
    maintenant = maintenant or datetime.now(timezone.utc)
    candidats, ameliorations = registre.lire_jsonl("candidats"), registre.lire_jsonl("ameliorations")
    exclus = {catalogue.normaliser(l) for l in registre.refuses()} | catalogue.inscrits()
    resultat = []
    for b in ouverts():
        age = round((maintenant - mesures.quand(b["depuis"])).total_seconds() / 3600)
        opts = options(b["id"], candidats, ameliorations, cas, exclus=exclus, retenus=catalogue.retenus())
        resultat.append({"id": b["id"], "par": b["par"], "besoin": b["besoin"], "manque": b["manque"],
                         "unite": b["unite"], "pourquoi": b["pourquoi"], "depuis": b["depuis"], "age_h": age,
                         "delai_h": DELAI_H, "delai_depasse": age > DELAI_H, "options": opts,
                         "note": None if opts else "aucune option trouvée par la Recherche pour l'instant"})
    return resultat


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    lignes = dossier()
    if not lignes:
        print("Aucun besoin ouvert")
    for b in lignes:
        retard = " (délai dépassé)" if b["delai_depasse"] else ""
        print(f"{b['id']} : il manque {b['manque']} {b['unite']}, depuis {b['age_h']} h{retard}\n  {b['besoin']}")
        for o in b["options"]:
            print(f"  - {o['genre']}, {o['voie']} : {o.get('nom') or o.get('id')} ({o['lien']})")
        if not b["options"]:
            print(f"  - {b['note']}")


if __name__ == "__main__":
    main()
