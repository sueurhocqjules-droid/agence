"""Chef de Contenu : fixe le nombre de sujets de la semaine et fait ses retours à l'Auteur et au Programmateur.

Lancement : python -m agence.lancer chef-contenu   (ou python -m agents.chef_contenu --essai : montre, n'écrit rien)

1. Script : jours de stock par chaîne, sujets écrits pas encore programmés, et le minimum de sujets pour tenir
   la consigne (7 jours de stock d'avance au dimanche suivant), entre 1 et le plafond : 14 (atelier) ou moins
   si le budget de la semaine (fiche de l'Auteur, ajusté par Jules) paie moins de sujets.
2. Modèle gratuit : choisit le nombre dans ces bornes, écrit les retours de son équipe et répond aux demandes
   de Jules (issues equipe:contenu). Le script vérifie tout (choix fermés) avant de l'appliquer.
3. Écrit organisation/plan.toml, que l'atelier (chaines-studio) lit le lundi, et note sa prédiction.
"""
import json
import math
import sys
from datetime import datetime, timedelta, timezone

from agence import consignes, demandes, lancer, mesures, modeles, postes, registre, youtube
from agents import flux, surete

PLAN = "organisation/plan.toml"
STOCK_VISE = 7      # jours, consigne de la fiche
SUJETS_MAX = 14     # plafond de l'atelier (atelier.yml)


def sujets_en_attente(sujets, titres, stats, stock):
    """Par chaîne, les sujets écrits qui n'y sont ni en ligne (titre jamais relevé) ni programmés par l'agence."""
    en_ligne = {(l["chaine"], l["titre"]) for l in stats}
    programmes = {l["nom"] for l in stock if l["etat"] == "programme"}
    return {langue: sum(1 for s in sujets if (langue, titres[s][langue]) not in en_ligne
                        and f"{s}-{langue}" not in programmes) for langue in youtube.CHAINES}


def besoin(stock, stats, heures, attente, maintenant):
    """(minimum de sujets à écrire, détail par chaîne) pour avoir STOCK_VISE jours d'avance dans 7 jours."""
    programmes = mesures.stock_programme(stock, stats, maintenant)
    detail, manque = {}, 0
    for langue, h in heures.items():
        a_couvrir = len(h) * (7 + STOCK_VISE)   # sorties d'ici la fin de la semaine prochaine
        detail[langue] = {"programmees": programmes[langue], "sujets_en_attente": attente[langue], "a_couvrir": a_couvrir}
        manque = max(manque, a_couvrir - programmes[langue] - attente[langue])
    return manque, detail


def videos_reperes(stats, maintenant):
    """Par chaîne, les 3 meilleures et les 3 moins bonnes vidéos de plus de 2 jours, au dernier relevé."""
    releve = max((l["releve"] for l in stats), default=None)
    agees = [l for l in stats if l["releve"] == releve and l["statut"] == "public" and mesures.quand(l["sortie"])
             and mesures.quand(l["sortie"]) <= maintenant - timedelta(days=2)]
    ligne = lambda l: f"« {l['titre']} » {l['vues']} vues"
    reperes = {}
    for chaine in youtube.CHAINES:
        videos = sorted((l for l in agees if l["chaine"] == chaine), key=lambda l: int(l["vues"]), reverse=True)
        if len(videos) >= 4:
            reperes[chaine] = {"meilleures": [ligne(l) for l in videos[:3]],
                               "moins_bonnes": [ligne(l) for l in videos[-3:][::-1] if l not in videos[:3]]}
    return reperes


def ecrire_plan(semaine, nombre, pourquoi):
    texte = ("# Plan de la semaine, écrit par le Chef de contenu (agents/chef_contenu.py) : l'atelier (chaines-studio) le lit le lundi.\n"
             f"semaine = {json.dumps(semaine)}\nnombre_de_sujets = {nombre}\npourquoi = {json.dumps(pourquoi, ensure_ascii=False)}\n")
    (consignes.RACINE / PLAN).write_text(texte, encoding="utf-8", newline="\n")


def retour_valide(texte):
    lignes = [l.strip()[:300] for l in str(texte or "").splitlines() if l.strip()]
    return "\n".join(lignes[:3]) if lignes else None


def passage(essai):
    maintenant = datetime.now(timezone.utc)
    lundi = (maintenant + timedelta(days=7 - maintenant.weekday())).date().isoformat()
    donnees = mesures.charger(surete.couts_atelier())
    sujets = flux.ordre_sujets()
    titres = {s: {l: flux.lire_sujet(s)[0][l]["titre"] for l in youtube.CHAINES} for s in sujets}
    attente = sujets_en_attente(sujets, titres, donnees["stats"], donnees["stock"])
    minimum, detail = besoin(donnees["stock"], donnees["stats"], donnees["heures"], attente, maintenant)
    capacite, cout, budget = mesures.capacite(donnees["atelier"])
    plafond = max(1, min(SUJETS_MAX, capacite)) if capacite is not None else SUJETS_MAX
    plancher = min(max(1, minimum), plafond)
    reperes = videos_reperes(donnees["stats"], maintenant)
    try:
        issues = demandes.demandes("contenu")
    except Exception as e:  # noqa: BLE001 : sans accès aux issues, le plan se fait quand même
        print(f"Demandes de Jules illisibles : {str(e)[:120]}")
        issues = []
    fiches = {p: consignes.chemin_fiche(p).read_text(encoding="utf-8") for p in ("chef-contenu", "auteur", "programmateur")}
    vues = {l: mesures.vues_gagnees(donnees["stats"], maintenant, l) for l in donnees["heures"]}
    jours = {l: mesures.jours_de_stock(donnees["stock"], donnees["stats"], donnees["heures"], maintenant, l)
             for l in donnees["heures"]}

    consigne = f"""Tu es le chef de contenu d'une agence de vidéos courtes (YouTube Shorts « Every Second » : une règle
absurde et ses vrais calculs, trois chaînes en, es, pt). Ta mission : le plus de vues possible dans le budget,
sans trou dans le calendrier. Tes consignes : {consignes.lire_section(fiches["chef-contenu"], "Consignes")}

Situation au {maintenant:%d/%m} :
- vues gagnées sur les 7 derniers jours par chaîne : {vues}
- jours de sorties programmées d'avance par chaîne : {jours}
- par chaîne : {json.dumps(detail, ensure_ascii=False)}
- l'atelier écrit lundi entre {plancher} (minimum pour tenir {STOCK_VISE} jours de stock dimanche prochain) et {plafond} sujets
  (ce que paie le budget de la semaine, {budget:.0f} $ à {cout if cout else "~2"} $ par sujet), chacun publié sur les trois
  chaînes. Au-delà du minimum, les sujets font du stock d'avance.
- vidéos de plus de 2 jours, par chaîne (comparer les sujets entre eux sur une même chaîne : les mêmes sujets sortent
  partout, un écart entre chaînes parle de la chaîne, pas des sujets) : {json.dumps(reperes, ensure_ascii=False) if reperes else "pas encore assez de recul"}
- chaînes que YouTube diffuse mal (la Direction s'en occupe ; n'en tire rien sur les sujets) : {"; ".join(p["texte"] for p in mesures.signaux_portee(donnees["stats"], maintenant)) or "aucune"}
- derniers retours à l'Auteur : {consignes.lire_section(fiches["auteur"], "Retours") or "aucun"}
- le Programmateur ne règle que les heures de sortie de chaque chaîne (actuelles, à Paris : {donnees["heures"]}) ;
  derniers retours qu'il a reçus : {consignes.lire_section(fiches["programmateur"], "Retours") or "aucun"}
- demandes de Jules (le propriétaire) à ton équipe : {json.dumps(issues, ensure_ascii=False) if issues else "aucune"}

N'écris aucun chiffre qui ne figure pas ci-dessus. Pas de demande de Jules : "reponses": [].
Réponds seulement en JSON, en français, sans tiret long :
{{"nombre": <entier entre {plancher} et {plafond}>, "pourquoi": "<une phrase>",
"retour_auteur": "<1 à 3 lignes : quels sujets marchent, quoi refaire ou éviter, chiffres à l'appui>",
"retour_programmateur": "<1 à 3 lignes sur les heures de sortie, ou vide si rien à dire>",
"reponses": [{{"numero": <numéro de l'issue>, "texte": "<réponse à Jules et ce que tu décides>"}}]}}"""
    texte, modele, *_ = postes.demander("chef-contenu", consigne)
    reponse = modeles.extraire_json(texte) or {}
    nombre = reponse.get("nombre")
    if not isinstance(nombre, int) or not plancher <= nombre <= plafond:
        print(f"Nombre proposé hors bornes ({nombre!r}) : minimum retenu")
        nombre = plancher
    pourquoi = str(reponse.get("pourquoi") or f"minimum pour {STOCK_VISE} jours de stock")[:300]
    resultat = f"{nombre} sujets pour la semaine du {lundi} ({modele}) : {pourquoi}"
    if essai:
        return resultat + f"\n{json.dumps(reponse, ensure_ascii=False, indent=1)[:1500]}", 1

    ecrire_plan(lundi, nombre, pourquoi)
    registre.decider("chef-contenu", f"{nombre} sujets à écrire la semaine du {lundi}",
                     f"{pourquoi} (stock actuel en jours : {jours}, minimum calculé : {minimum})",
                     prediction=f"au moins {STOCK_VISE} jours de stock sur chaque chaîne dans 7 jours",
                     mesure="jours_de_stock", attendu=STOCK_VISE,
                     echeance=(maintenant + timedelta(days=7)).isoformat(timespec="seconds"))
    consignes.commiter([consignes.RACINE / PLAN], f"Chef de contenu : {nombre} sujets la semaine du {lundi}")
    for poste in ("auteur", "programmateur"):
        retour = retour_valide(reponse.get(f"retour_{poste}"))
        if retour:
            consignes.ajouter_retour(poste, "chef-contenu", retour)
    numeros = {i["numero"] for i in issues}
    for r in reponse.get("reponses") or []:
        if isinstance(r, dict) and r.get("numero") in numeros and str(r.get("texte") or "").strip():
            demandes.repondre(r["numero"], f"{str(r['texte']).strip()[:2000]}\n\n_Le Chef de contenu de l'agence._")
            registre.decider("chef-contenu", f"réponse à la demande #{r['numero']}", str(r["texte"])[:300])
    if minimum > plafond:  # remonte à la Direction, qui lit les blocages des journaux
        lancer.noter_journal("chef-contenu", {"date": registre.maintenant(), "quoi": "plan", "resultat": "ok",
                                              "bloquant": f"il faudrait {minimum} sujets pour tenir {STOCK_VISE} jours "
                                                          f"de stock, le budget et l'atelier en permettent {plafond}. "
                                                          f"Le Programmateur baisse la cadence si le stock passe sous 3 jours"})
    return resultat, 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--essai" in sys.argv:
        print(passage(essai=True)[0])
        return
    with registre.seance("chef-contenu") as info:
        resultat, appels = passage(essai=False)
        info["appels_gratuits"] = appels
        info["resultat"] = f"ok : {resultat}"[:200]
        print(info["resultat"])


if __name__ == "__main__":
    main()
