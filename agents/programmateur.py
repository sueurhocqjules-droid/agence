"""Programmateur : décide, chaîne par chaîne, de la cadence (sorties par jour) et des heures de sortie, dans le budget.

Lancement : python -m agence.lancer programmateur   (ou python -m agents.programmateur --essai)

1. Script : vues de chaque vidéo à 48 h par chaîne et par heure, coût d'un sujet, sujets que paie le budget de la semaine
   (fiche de l'Auteur, ajusté par Jules), jours de stock.
2. Budget trop court et stock presque vide : la cadence baisse tout de suite (une sortie de moins par jour sur les
   chaînes les plus rapides), sans attendre ni le modèle ni l'essai en cours.
3. Sinon, un essai à la fois (consigne de sa fiche), et seulement avec assez de données : un modèle gratuit propose au
   plus un changement (déplacer, ajouter ou retirer une heure sur une chaîne) avec sa prédiction. Le script le vérifie
   (choix fermés : une hausse de cadence doit tenir dans le budget) et l'applique à organisation/creneaux.toml, que le
   flux lit. Le critique le juge au bout de deux semaines et l'annule s'il n'a rien amélioré.
"""
import statistics
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from agence import consignes, mesures, modeles, postes, registre, youtube
from agents import surete

PARIS = ZoneInfo("Europe/Paris")
FICHIER = "organisation/creneaux.toml"
ESSAI_JOURS = 14
VIDEOS_MIN = 12     # par chaîne, avec leurs vues à 48 h, avant de proposer un essai
CADENCE_MAX = 3     # sorties par jour et par chaîne (quota d'envoi YouTube partagé par les trois chaînes)
STOCK_ALERTE = 3    # jours : en dessous, si le budget ne paie pas la cadence, elle baisse sans attendre


def vues_a_48h(stats):
    """{(chaine, heure de sortie à Paris): [vues à 48 h, ...]} pour les vidéos qui ont un relevé 48 h après leur sortie."""
    premieres = {}
    for l in sorted(stats, key=lambda l: l["releve"]):
        sortie = mesures.quand(l["sortie"])
        if l["statut"] != "public" or not sortie or (l["chaine"], l["video_id"]) in premieres:
            continue
        if mesures.quand(l["releve"]) >= sortie + timedelta(hours=48):
            premieres[(l["chaine"], l["video_id"])] = (sortie.astimezone(PARIS).hour, int(l["vues"]))
    groupes = {}
    for (chaine, _), (heure, vues) in premieres.items():
        groupes.setdefault((chaine, heure), []).append(vues)
    return groupes


def tableau(groupes):
    return "\n".join(f"{c} {h}h : {len(v)} vidéos, médiane {statistics.median(v):.0f} vues à 48 h"
                     for (c, h), v in sorted(groupes.items()))


def ecrire_creneaux(heures):
    lignes = ["# Heures de sortie des vidéos, à Paris, par chaîne : le flux les applique, dans l'ordre de la journée.",
              "# Propriétaire : le Programmateur, un seul changement à la fois, jugé par le critique au bout de deux semaines.", ""]
    for langue, h in heures.items():
        lignes += [f"[{langue}]", f"heures = [{', '.join(map(str, sorted(h)))}]", ""]
    return "\n".join(lignes).rstrip() + "\n"


def valider(proposition, heures, avants, capacite):
    """Renvoie (chaine, nouvelles heures, attendu) si la proposition respecte les choix fermés, sinon lève ValueError.

    ancienne et nouvelle : déplacer une heure. nouvelle seule : une sortie de plus par jour. ancienne seule : une de moins.
    Chaque sujet sort sur les trois chaînes : la chaîne la plus rapide fixe le nombre de sujets à payer par semaine.
    """
    chaine, ancienne, nouvelle = proposition.get("chaine"), proposition.get("ancienne"), proposition.get("nouvelle")
    attendu, avant = proposition.get("attendu"), avants.get(chaine)
    if chaine not in heures:
        raise ValueError(f"chaîne inconnue : {chaine!r}")
    actuelles = heures[chaine]
    if ancienne is None and nouvelle is None:
        raise ValueError("ni heure retirée ni heure ajoutée")
    if ancienne is not None and ancienne not in actuelles:
        raise ValueError(f"heure retirée absente : {ancienne!r} (actuelles : {actuelles})")
    if nouvelle is not None and (not isinstance(nouvelle, int) or not 0 <= nouvelle <= 23 or nouvelle in actuelles):
        raise ValueError(f"heure ajoutée invalide : {nouvelle!r} (actuelles : {actuelles})")
    nouvelles = sorted([h for h in actuelles if h != ancienne] + ([nouvelle] if nouvelle is not None else []))
    if not 1 <= len(nouvelles) <= CADENCE_MAX:
        raise ValueError(f"cadence hors de 1 à {CADENCE_MAX} sorties par jour : {len(nouvelles)}")
    rythme = max(len(h) for h in {**heures, chaine: nouvelles}.values())
    if len(nouvelles) > len(actuelles) and (capacite is None or 7 * rythme > capacite):
        raise ValueError(f"hausse de cadence hors budget : {7 * rythme} sujets par semaine, le budget en paie {capacite}")
    if avant is None or not isinstance(attendu, (int, float)) or not avant < attendu <= 3 * max(avant, 1):
        raise ValueError(f"prédiction invalide : {attendu!r} vues attendues pour {avant!r} avant")
    return chaine, nouvelles, attendu


def reduction_forcee(heures, groupes):
    """Une sortie de moins par jour sur chaque chaîne au rythme le plus haut : l'heure à la plus faible médiane de
    vues à 48 h, la plus tardive sans données. Aucune chaîne ne descend sous une sortie par jour."""
    rythme = max(len(h) for h in heures.values())
    if rythme <= 1:
        return heures
    rang = lambda c, h: (statistics.median(groupes[(c, h)]) if (c, h) in groupes else float("-inf"), -h)
    return {c: sorted(set(h) - {min(h, key=lambda x: rang(c, x))}) if len(h) == rythme else h
            for c, h in heures.items()}


def passage(essai):
    maintenant = datetime.now(timezone.utc)
    donnees = mesures.charger(surete.couts_atelier())
    heures, groupes = donnees["heures"], vues_a_48h(donnees["stats"])
    capacite, cout, budget = mesures.capacite(donnees["atelier"])
    rythme = max(len(h) for h in heures.values())
    jours = {c: mesures.jours_de_stock(donnees["stock"], donnees["stats"], heures, maintenant, c) for c in heures}
    attente = consignes.en_attente("creneaux")

    if capacite is not None and 7 * rythme > capacite and min(jours.values()) < STOCK_ALERTE and rythme > 1:
        nouvelles = reduction_forcee(heures, groupes)
        raison = (f"le budget de la semaine ({budget:.0f} $, {cout} $ par sujet) paie {capacite} sujets, la cadence en "
                  f"demande {7 * rythme}, et le stock n'a plus que {min(jours.values())} jours sur la chaîne la moins fournie")
        if essai:
            return f"ESSAI : réduction forcée {heures} vers {nouvelles} ({raison})", 0
        if attente:
            registre.juger(attente["id"], "indeterminee", None, "essai interrompu : cadence réduite faute de budget")
        (consignes.RACINE / FICHIER).write_text(ecrire_creneaux(nouvelles), encoding="utf-8", newline="\n")
        registre.decider("programmateur", f"cadence réduite : {heures} vers {nouvelles}", raison,
                         prediction=f"au moins {STOCK_ALERTE} jours de stock sur chaque chaîne dans 14 jours",
                         mesure="jours_de_stock", avant=min(jours.values()), attendu=STOCK_ALERTE,
                         echeance=(maintenant + timedelta(days=14)).isoformat(timespec="seconds"))
        consignes.commiter([consignes.RACINE / FICHIER, registre.DOSSIER / "decisions.jsonl"],
                           "Programmateur : cadence réduite faute de budget")
        return f"cadence réduite faute de budget : {nouvelles}", 0

    if attente:
        return f"essai en cours ({attente['decision']}), jugé le {attente['echeance'][:10]} : rien ne change", 0
    par_chaine = {c: sum(len(v) for (cc, _), v in groupes.items() if cc == c) for c in youtube.CHAINES}
    if min(par_chaine.values()) < VIDEOS_MIN:
        return f"trop tôt : vidéos avec leurs vues à 48 h par chaîne {par_chaine}, il en faut {VIDEOS_MIN}", 0
    avants = {c: mesures.valeur(f"vues_semaine:{c}", maintenant, donnees) for c in heures}
    fiche = consignes.chemin_fiche("programmateur").read_text(encoding="utf-8")
    consigne = f"""Tu es le programmateur d'une agence de vidéos courtes (YouTube Shorts, trois chaînes : en, es, pt).
Tu décides de la cadence (sorties par jour, de 1 à {CADENCE_MAX}) et des heures de sortie de chaque chaîne, en t'appuyant
sur ce que tu sais des pratiques qui marchent sur chaque réseau et sur les chiffres ci-dessous.
Heures de sortie actuelles, à Paris : {heures}
Vues gagnées sur les 7 derniers jours par chaîne : {avants}
Vues à 48 h selon l'heure de sortie :
{tableau(groupes)}
Budget : chaque sujet sort sur les trois chaînes, la chaîne la plus rapide fixe donc le nombre de sujets à écrire par
semaine ({7 * rythme} aujourd'hui). Le budget de la semaine ({budget:.0f} $, {cout if cout else "coût inconnu"} $ par sujet)
en paie {capacite if capacite is not None else "un nombre encore inconnu"}. Jours de sorties programmées d'avance : {jours}.

Tes consignes : {consignes.lire_section(fiche, "Consignes")}
Retours de ton chef : {consignes.lire_section(fiche, "Retours") or "aucun"}

Propose au plus UN essai, s'il y a une raison dans les chiffres : déplacer une heure (ancienne et nouvelle), ajouter
une sortie par jour (nouvelle seule, seulement si le budget la paie) ou en retirer une (ancienne seule). Sinon, aucun
essai. L'essai dure deux semaines. Réponds seulement en JSON :
{{"changement": null}}
ou {{"changement": {{"chaine": "en", "ancienne": <heure ou null>, "nouvelle": <heure ou null>, "attendu": <vues gagnées
sur 7 jours attendues sur cette chaîne dans deux semaines, plus que la valeur actuelle>, "pourquoi": "<une phrase,
chiffres à l'appui>"}}}}"""
    texte, modele, *_ = postes.demander("programmateur", consigne)
    reponse = modeles.extraire_json(texte) or {}
    proposition = reponse.get("changement")
    if not proposition:
        if not essai:
            registre.decider("programmateur", "pas d'essai de créneaux cette semaine",
                             f"choix du modèle {modele} sur les chiffres")
        return "pas d'essai cette semaine", 1
    try:
        chaine, nouvelles, attendu = valider(proposition, heures, avants, capacite)
    except ValueError as e:
        if not essai:
            registre.decider("programmateur", "proposition de créneaux refusée par le script", str(e))
        return f"proposition refusée : {e}", 1
    if essai:
        return f"ESSAI : {chaine} {heures[chaine]} vers {nouvelles}, {attendu} vues attendues", 1
    consignes.changer("creneaux", "programmateur", FICHIER, ecrire_creneaux({**heures, chaine: nouvelles}),
                      f"{chaine} : {heures[chaine]} vers {nouvelles}. {str(proposition.get('pourquoi', ''))[:300]}",
                      f"vues_semaine:{chaine}", avants[chaine], attendu, ESSAI_JOURS)
    return f"essai lancé : {chaine} {heures[chaine]} vers {nouvelles}", 1


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--essai" in sys.argv:
        print(passage(essai=True)[0])
        return
    with registre.seance("programmateur") as info:
        resultat, appels = passage(essai=False)
        info["appels_gratuits"] = appels
        info["resultat"] = f"ok : {resultat}"[:200]
        print(info["resultat"])


if __name__ == "__main__":
    main()
