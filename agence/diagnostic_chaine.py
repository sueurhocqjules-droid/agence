"""Diagnostic de la chaîne espagnole contre la chaîne portugaise (propriétaire : chef-contenu).

Lancé par le flux, avec les jetons YouTube qu'il a déjà. Pour es et pt, il lit :
- la chaîne (channels.list) : status.madeForKids, selfDeclaredMadeForKids, longUploadsStatus,
  brandingSettings.channel.country et defaultLanguage ;
- les 14 dernières vidéos (videos.list) : statut (privacyStatus, madeForKids, selfDeclaredMadeForKids, license,
  embeddable), contentDetails (contentRating, regionRestriction), snippet (defaultLanguage, defaultAudioLanguage,
  categoryId). Les vidéos sont mises en face l'une de l'autre par rang (les mêmes sujets sortent sur les deux).
Il écrit chaque différence dans registre/diagnostic-chaines.json.

Il corrige seul deux cas, et rien d'autre :
1. « public enfants » à vrai sur es alors que pt est à faux (chaîne par channels.update, vidéo par videos.update) ;
2. vidéo privée ou non répertoriée sur es alors que sa jumelle pt est publique (hors vidéo programmée).
Chaque correction va au journal d'audit. Ce qui reste inexpliqué devient un bloquant du chef-contenu
(registre/journal/chef-contenu.jsonl), noté une seule fois tant que le diagnostic ne change pas.
Coût : 0 jeton, une dizaine d'unités de quota YouTube par passage.
"""
import json

from agence import registre

NOMBRE = 14
FICHIER = registre.DOSSIER / "diagnostic-chaines.json"
PROPRIETAIRE = "chef-contenu"
CHAMPS_LANGUE = {"country", "defaultLanguage", "defaultAudioLanguage"}   # il est normal qu'ils diffèrent
PARTIES_CHAINE = "id,status,brandingSettings"
PARTIES_VIDEO = "snippet,status,contentDetails"


def champs_chaine(item):
    statut, marque = item.get("status", {}), item.get("brandingSettings", {}).get("channel", {})
    return {"madeForKids": statut.get("madeForKids"), "selfDeclaredMadeForKids": statut.get("selfDeclaredMadeForKids"),
            "longUploadsStatus": statut.get("longUploadsStatus"), "country": marque.get("country"),
            "defaultLanguage": marque.get("defaultLanguage")}


def champs_video(item):
    statut, details, snippet = item.get("status", {}), item.get("contentDetails", {}), item.get("snippet", {})
    return {"privacyStatus": statut.get("privacyStatus"), "madeForKids": statut.get("madeForKids"),
            "selfDeclaredMadeForKids": statut.get("selfDeclaredMadeForKids"), "license": statut.get("license"),
            "embeddable": statut.get("embeddable"), "contentRating": details.get("contentRating") or None,
            "regionRestriction": details.get("regionRestriction"), "defaultLanguage": snippet.get("defaultLanguage"),
            "defaultAudioLanguage": snippet.get("defaultAudioLanguage"), "categoryId": snippet.get("categoryId")}


def lire_chaine(youtube):
    item = youtube.channels().list(part=PARTIES_CHAINE, mine=True).execute()["items"][0]
    return item["id"], champs_chaine(item)


def lire_videos(youtube, nombre=NOMBRE):
    """Les dernières vidéos de la chaîne (la plus récente d'abord) : liste de (id, champs, publishAt)."""
    envois = youtube.channels().list(part="contentDetails", mine=True).execute()[
        "items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids = [i["contentDetails"]["videoId"] for i in youtube.playlistItems().list(
        part="contentDetails", playlistId=envois, maxResults=nombre).execute()["items"]]
    if not ids:
        return []
    items = {v["id"]: v for v in youtube.videos().list(part=PARTIES_VIDEO, id=",".join(ids)).execute()["items"]}
    return [(i, champs_video(items[i]), items[i].get("status", {}).get("publishAt")) for i in ids if i in items]


def differences(chaines, videos):
    """Chaque différence es / pt : dicts niveau, rang (vidéos), champ, es, pt."""
    liste = [{"niveau": "chaine", "champ": c, "es": chaines["es"][c], "pt": chaines["pt"][c]}
             for c in chaines["es"] if chaines["es"][c] != chaines["pt"][c]]
    for rang, (es, pt) in enumerate(zip(videos["es"], videos["pt"])):
        liste += [{"niveau": "video", "rang": rang, "video_es": es[0], "video_pt": pt[0], "champ": c,
                   "es": es[1][c], "pt": pt[1][c]} for c in es[1] if es[1][c] != pt[1][c]]
    return liste


def explique(d):
    """Une différence de langue ou de pays est normale quand chaque chaîne reste dans sa langue (ou ne dit rien)."""
    if d["champ"] == "country":   # ES d'un côté, PT ou BR de l'autre : le pays est choisi par chaîne
        return True
    return (d["champ"] in CHAMPS_LANGUE and (d["es"] is None or str(d["es"]).lower().startswith("es"))
            and (d["pt"] is None or str(d["pt"]).lower().startswith("pt")))


def enfants(valeur):
    return valeur is True


def corriger(clients, chaines, videos, ident_chaine):
    """Les deux corrections permises. Renvoie (corrections faites, échecs). Chaque correction est notée à l'audit."""
    faites, echecs = [], []

    def essayer(quoi, pourquoi, prediction, appel):
        try:
            appel()
        except Exception as erreur:   # droit manquant, quota... : la différence reste, et devient un bloquant
            echecs.append({"correction": quoi, "erreur": str(erreur)[:300]})
            return
        faites.append(quoi)
        registre.decider(PROPRIETAIRE, f"correction YouTube : {quoi}", pourquoi, prediction=prediction)

    youtube = clients["es"]
    if enfants(chaines["es"]["selfDeclaredMadeForKids"]) and chaines["pt"]["selfDeclaredMadeForKids"] is False:
        essayer("chaîne es : « public enfants » remis à faux",
                "es est déclarée pour les enfants, pas pt : YouTube limite alors la diffusion (diagnostic #33)",
                "les vues de la chaîne es remontent vers celles de pt",
                lambda: youtube.channels().update(part="status", body={
                    "id": ident_chaine, "status": {"selfDeclaredMadeForKids": False}}).execute())
    for (ident, champs_es, programmee), (_, champs_pt, _) in zip(videos["es"], videos["pt"]):
        statut = {}
        if enfants(champs_es["selfDeclaredMadeForKids"]) and champs_pt["selfDeclaredMadeForKids"] is False:
            statut["selfDeclaredMadeForKids"] = False
        if champs_es["privacyStatus"] in ("private", "unlisted") and champs_pt["privacyStatus"] == "public" \
                and not programmee:
            statut["privacyStatus"] = "public"
        if not statut:
            continue
        item = youtube.videos().list(part="status", id=ident).execute()["items"][0]["status"]
        corps = {k: item[k] for k in ("privacyStatus", "embeddable", "license", "publicStatsViewable") if k in item}
        corps.update(statut)
        essayer(f"vidéo es {ident} : {', '.join(f'{k} = {v}' for k, v in statut.items())}",
                "la jumelle pt est publique ou non enfants, pas celle-ci (diagnostic #33)",
                "la vidéo es est diffusée comme sa jumelle pt",
                lambda ident=ident, corps=corps: youtube.videos().update(
                    part="status", body={"id": ident, "status": corps}).execute())
    return faites, echecs


def diagnostiquer(clients):
    """Lit, compare, corrige, écrit le fichier et note le bloquant. Renvoie le contenu écrit."""
    ident_chaine, chaines, videos = None, {}, {}
    for langue in ("es", "pt"):
        ident, chaines[langue] = lire_chaine(clients[langue])
        videos[langue] = lire_videos(clients[langue])
        if langue == "es":
            ident_chaine = ident
    liste = differences(chaines, videos)
    faites, echecs = corriger(clients, chaines, videos, ident_chaine)
    restantes = [d for d in liste if not explique(d)]
    if faites:   # les différences corrigées ne sont plus d'actualité : on relit pour que le fichier dise le vrai
        ident, chaines["es"] = lire_chaine(clients["es"])
        videos["es"] = lire_videos(clients["es"])
        liste = differences(chaines, videos)
        restantes = [d for d in liste if not explique(d)]
    contenu = {"releve": registre.maintenant(), "videos_comparees": min(len(videos["es"]), len(videos["pt"])),
               "chaines": chaines, "differences": liste, "corrections": faites, "echecs": echecs,
               "inexpliquees": len(restantes) + len(echecs)}
    ecrire(contenu, restantes, echecs)
    return contenu


def resume(restantes, echecs, comparees):
    morceaux = [f"{d['champ']} : es {d['es']} contre pt {d['pt']}" for d in restantes[:6]]
    morceaux += [f"correction refusée ({e['correction']}) : {e['erreur']}" for e in echecs[:3]]
    if not morceaux:
        return (f"es et pt ne diffèrent sur aucun des champs lus ({comparees} vidéos comparées) : "
                "la cause du faible nombre de vues n'est pas dans ces réglages")
    return "écarts es / pt sans explication : " + " ; ".join(morceaux)


def ecrire(contenu, restantes, echecs):
    """Écrit le fichier ; le bloquant n'est noté que si le diagnostic a changé depuis le précédent."""
    cle = lambda c: json.dumps([c.get("differences"), c.get("echecs")], sort_keys=True, ensure_ascii=False)
    ancien = json.loads(FICHIER.read_text(encoding="utf-8")) if FICHIER.exists() else None
    if ancien is not None and cle(ancien) == cle(contenu) and not contenu["corrections"]:
        return
    FICHIER.write_text(json.dumps(contenu, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if contenu["inexpliquees"] or not contenu["corrections"]:   # reste à expliquer, ou rien n'a expliqué l'écart
        from agence import lancer
        lancer.noter_journal(PROPRIETAIRE, {"date": registre.maintenant(), "quoi": "diagnostic_chaine",
                                            "resultat": "bloquant",
                                            "bloquant": resume(restantes, echecs, contenu["videos_comparees"])})


def main():
    from agence import youtube
    return diagnostiquer({langue: youtube.client(langue) for langue in ("es", "pt")})
