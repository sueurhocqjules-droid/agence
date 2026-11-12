"""Programmateur : cherche, chaîne par chaîne, les heures de sortie qui apportent le plus de vues.

Lancement : python -m agence.lancer programmateur   (ou python -m agents.programmateur --essai)

1. Script : vues de chaque vidéo à 48 h, rangées par chaîne et par heure de sortie (Paris).
2. Un essai à la fois (consigne de sa fiche) : tant que le précédent n'est pas jugé, rien ne change.
3. Assez de données : un modèle gratuit propose au plus un déplacement d'heure sur une chaîne, avec sa prédiction.
   Le script le vérifie (choix fermés) et l'applique à organisation/creneaux.toml, que le flux lit.
   Le critique le juge au bout de deux semaines et l'annule s'il n'a rien amélioré.
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
VIDEOS_MIN = 12   # par chaîne, avec leurs vues à 48 h, avant de proposer un essai


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


def valider(proposition, heures, avants):
    """Renvoie (chaine, nouvelles heures, attendu) si la proposition respecte les choix fermés, sinon lève ValueError."""
    chaine, ancienne, nouvelle = proposition.get("chaine"), proposition.get("ancienne"), proposition.get("nouvelle")
    attendu, avant = proposition.get("attendu"), avants.get(chaine)
    if chaine not in heures:
        raise ValueError(f"chaîne inconnue : {chaine!r}")
    if ancienne not in heures[chaine] or not isinstance(nouvelle, int) or not 0 <= nouvelle <= 23 or nouvelle in heures[chaine]:
        raise ValueError(f"heures invalides : {ancienne!r} vers {nouvelle!r} (actuelles : {heures[chaine]})")
    if avant is None or not isinstance(attendu, (int, float)) or not avant < attendu <= 3 * max(avant, 1):
        raise ValueError(f"prédiction invalide : {attendu!r} vues attendues pour {avant!r} avant")
    return chaine, sorted([h for h in heures[chaine] if h != ancienne] + [nouvelle]), attendu


def passage(essai):
    maintenant = datetime.now(timezone.utc)
    attente = consignes.en_attente("creneaux")
    if attente:
        return f"essai en cours ({attente['decision']}), jugé le {attente['echeance'][:10]} : rien ne change", 0
    donnees = mesures.charger(surete.couts_atelier())
    groupes = vues_a_48h(donnees["stats"])
    par_chaine = {c: sum(len(v) for (cc, _), v in groupes.items() if cc == c) for c in youtube.CHAINES}
    if min(par_chaine.values()) < VIDEOS_MIN:
        return f"trop tôt : vidéos avec leurs vues à 48 h par chaîne {par_chaine}, il en faut {VIDEOS_MIN}", 0
    heures = donnees["heures"]
    avants = {c: mesures.valeur(f"vues_semaine:{c}", maintenant, donnees) for c in heures}
    fiche = consignes.chemin_fiche("programmateur").read_text(encoding="utf-8")
    consigne = f"""Tu es le programmateur d'une agence de vidéos courtes (YouTube Shorts, trois chaînes : en, es, pt).
Heures de sortie actuelles, à Paris : {heures}
Vues gagnées sur les 7 derniers jours par chaîne : {avants}
Vues à 48 h selon l'heure de sortie :
{tableau(groupes)}

Tes consignes : {consignes.lire_section(fiche, "Consignes")}
Retours de ton chef : {consignes.lire_section(fiche, "Retours") or "aucun"}

Propose au plus UN essai : déplacer une heure de sortie d'une chaîne vers une autre heure, s'il y a une raison
dans les chiffres. Sinon, aucun essai. L'essai dure deux semaines. Réponds seulement en JSON :
{{"changement": null}}
ou {{"changement": {{"chaine": "en", "ancienne": 18, "nouvelle": 20, "attendu": <vues gagnées sur 7 jours attendues
sur cette chaîne dans deux semaines, plus que la valeur actuelle>, "pourquoi": "<une phrase, chiffres à l'appui>"}}}}"""
    texte, modele, *_ = postes.demander("programmateur", consigne)
    reponse = modeles.extraire_json(texte) or {}
    proposition = reponse.get("changement")
    if not proposition:
        if not essai:
            registre.decider("programmateur", "pas d'essai de créneaux cette semaine",
                             f"choix du modèle {modele} sur les chiffres")
        return "pas d'essai cette semaine", 1
    try:
        chaine, nouvelles, attendu = valider(proposition, heures, avants)
    except ValueError as e:
        if not essai:
            registre.decider("programmateur", "proposition de créneaux refusée par le script", str(e))
        return f"proposition refusée : {e}", 1
    if essai:
        return f"ESSAI : {chaine} {heures[chaine]} vers {nouvelles}, {attendu} vues attendues", 1
    consignes.changer("creneaux", "programmateur", FICHIER, ecrire_creneaux({**heures, chaine: nouvelles}),
                      f"{chaine} : {proposition['ancienne']}h vers {proposition['nouvelle']}h. {str(proposition.get('pourquoi', ''))[:300]}",
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
