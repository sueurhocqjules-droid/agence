"""Diagnostic des réglages de la chaîne es face à la chaîne pt (demande #108, leçon du 13/11 de MEMOIRE.md).

    python -m agence.diagnostic_chaines   compare es et pt, écrit les différences au journal du chef de contenu

En lecture seule : l'API YouTube n'est interrogée que par `list`, rien n'est modifié sur les chaînes. Pour chaque
chaîne : public enfants, langue par défaut, pays. Pour chaque vidéo : statut (confidentialité, envoi, refus),
public enfants, langue, licence, intégration, restrictions de région. Les titres de es et de pt ne se
correspondent pas toujours : on compare les réglages de chaque chaîne, puis la répartition des valeurs sur ses
vidéos. Les différences vont dans `registre/journal/chef-contenu.jsonl` (`quoi = diagnostic_chaines`).
"""
import collections
import sys

from agence import lancer, registre, youtube

COMPARES = ("es", "pt")
REGLAGES_VIDEO = ("privacyStatus", "uploadStatus", "rejectionReason", "failureReason", "madeForKids",
                  "selfDeclaredMadeForKids", "license", "embeddable", "publicStatsViewable", "defaultLanguage",
                  "defaultAudioLanguage", "regionRestriction")


def reglages_chaine(item):
    """Les réglages d'une chaîne, à plat, depuis une réponse channels.list (snippet, status, brandingSettings)."""
    snippet, statut = item.get("snippet", {}), item.get("status", {})
    marque = item.get("brandingSettings", {}).get("channel", {})
    return {
        "madeForKids": statut.get("madeForKids"),
        "selfDeclaredMadeForKids": statut.get("selfDeclaredMadeForKids"),
        "privacyStatus": statut.get("privacyStatus"),
        "isLinked": statut.get("isLinked"),
        "defaultLanguage": snippet.get("defaultLanguage") or marque.get("defaultLanguage"),
        "country": snippet.get("country") or marque.get("country"),
    }


def reglages_video(video):
    """Les réglages d'une vidéo, à plat (parties snippet, status, contentDetails)."""
    snippet, statut = video.get("snippet", {}), video.get("status", {})
    brut = dict(statut)
    brut["defaultLanguage"] = snippet.get("defaultLanguage")
    brut["defaultAudioLanguage"] = snippet.get("defaultAudioLanguage")
    brut["regionRestriction"] = video.get("contentDetails", {}).get("regionRestriction")
    return {nom: brut.get(nom) for nom in REGLAGES_VIDEO}


def repartition(videos):
    """Par réglage, combien de vidéos portent chaque valeur : {réglage: {valeur: nombre}}."""
    compte = {nom: collections.Counter() for nom in REGLAGES_VIDEO}
    for video in videos:
        for nom, valeur in reglages_video(video).items():
            compte[nom][str(valeur)] += 1
    return {nom: dict(c) for nom, c in compte.items()}


def comparer(a, b):
    """Les réglages qui diffèrent entre deux dictionnaires de même forme : {réglage: (valeur a, valeur b)}."""
    return {nom: (a.get(nom), b.get(nom)) for nom in sorted(set(a) | set(b)) if a.get(nom) != b.get(nom)}


def diagnostic(chaines, videos):
    """chaines et videos : {langue: réponse de l'API}. Rend les différences es/pt, chaîne puis vidéos."""
    ref, autre = COMPARES
    return {
        "chaine": comparer(reglages_chaine(chaines[ref]), reglages_chaine(chaines[autre])),
        "videos": comparer(repartition(videos[ref]), repartition(videos[autre])),
        "nombre_videos": {langue: len(videos[langue]) for langue in COMPARES},
    }


def resume(resultat):
    ref, autre = COMPARES
    nombres = resultat["nombre_videos"]
    lignes = [f"diagnostic {ref} / {autre} : {nombres[ref]} et {nombres[autre]} vidéos"]
    for portee in ("chaine", "videos"):
        diff = resultat[portee]
        if not diff:
            lignes.append(f"{portee} : aucune différence")
        for nom, (x, y) in diff.items():
            lignes.append(f"{portee} {nom} : {ref}={x} {autre}={y}")
    return "\n".join(lignes)


def lire(langue):
    """Interroge l'API en lecture seule : la chaîne connectée et toutes ses vidéos."""
    api = youtube.client(langue)
    chaine = api.channels().list(part="snippet,status,brandingSettings", mine=True).execute()["items"][0]
    return chaine, youtube.videos(api, "snippet,status,contentDetails")


def main():
    chaines, videos = {}, {}
    for langue in COMPARES:
        chaines[langue], videos[langue] = lire(langue)
    resultat = diagnostic(chaines, videos)
    texte = resume(resultat)
    lancer.noter_journal("chef-contenu", {"date": registre.maintenant(), "quoi": "diagnostic_chaines",
                                          "resultat": "ok", "differences": resultat, "sortie": texte})
    print(texte)


if __name__ == "__main__":
    sys.exit(main())
