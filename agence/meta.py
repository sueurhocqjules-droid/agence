"""Accès à l'API Graph de Meta : comptes Instagram et Pages Facebook de l'agence.

Un seul jeton : l'utilisateur système `every-second-publisher` du portefeuille « Every Second Lab », sans expiration,
avec les 3 comptes Instagram et les 3 Pages assignés. Variable META_TOKEN (secret GitHub), sinon INSTAGRAM_ACCESS_TOKEN
du .env de Jarvis (même jeton, posé par `instagram.py login`).
Facebook : la vidéo part depuis le fichier (rupload.facebook.com). Instagram : Meta va la chercher à une adresse publique
(flux.heberger). Testé le 13/11 : l'envoi direct Instagram (rupload, « ProcessingFailedError ») et le lien du Reel Facebook
(erreur 2207076) échouent, une adresse raw.githubusercontent.com passe.
Docs : developers.facebook.com/docs/instagram-platform/content-publishing (Reels)
et developers.facebook.com/docs/video-api/guides/reels-publishing (Reels des Pages).
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

VERSION = "v27.0"
GRAPH = f"https://graph.facebook.com/{VERSION}/"
INSTAGRAM = {"en": "everysecondlab", "es": "cadasegundolab", "pt": "acadasegundolab"}
PAGES = {"en": "1537802816072828", "es": "1517937254731092", "pt": "1522397427617458"}
JARVIS_ENV = Path(__file__).resolve().parents[2] / "jarvis-starter-kit" / ".env"
LEGENDE_MAX = 2200  # limite d'Instagram


class ErreurMeta(RuntimeError):
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def jeton():
    brut = os.environ.get("META_TOKEN")
    if not brut and JARVIS_ENV.exists():
        for ligne in JARVIS_ENV.read_text(encoding="utf-8-sig").splitlines():
            nom, sep, valeur = ligne.partition("=")
            if sep and nom.strip() == "INSTAGRAM_ACCESS_TOKEN":
                brut = valeur.strip().strip('"')
    return brut or None


def appel(methode, chemin, params=None, cle=None, corps=None, entetes=None):
    """Appel à l'API Graph (paramètres en formulaire) ou envoi brut d'un fichier (corps, en-tête OAuth).
    Le jeton n'apparaît jamais dans un message d'erreur."""
    cle = cle or jeton()
    url = chemin if chemin.startswith("https://") else GRAPH + chemin
    params = {k: v for k, v in (params or {}).items() if v is not None}
    entetes = dict(entetes or {})
    if corps is None:
        params["access_token"] = cle
        encode = urllib.parse.urlencode(params)
        donnees = encode.encode() if methode == "POST" else None
        if methode == "GET":
            url += "?" + encode
    else:
        donnees = corps
        entetes["Authorization"] = f"OAuth {cle}"
    requete = urllib.request.Request(url, data=donnees, method=methode, headers=entetes)
    try:
        with urllib.request.urlopen(requete, timeout=300) as reponse:
            return json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            erreur = json.loads(e.read()).get("error", {})
        except ValueError:
            erreur = {}
        cible = chemin.split("?")[0] if not chemin.startswith("https://") else "envoi du fichier"
        raise ErreurMeta(f"{methode} {cible} : {erreur.get('message') or e.reason}", erreur.get("code")) from None


def liste(chemin, params, cle=None, maximum=200):
    """Toutes les lignes d'une liste paginée (curseur « after »), jusqu'à `maximum`."""
    lignes, apres = [], None
    while len(lignes) < maximum:
        reponse = appel("GET", chemin, {**params, "limit": 50, "after": apres}, cle)
        lignes += reponse.get("data", [])
        apres = ((reponse.get("paging") or {}).get("cursors") or {}).get("after")
        if not apres or not (reponse.get("paging") or {}).get("next"):
            break
    return lignes[:maximum]


def comptes_instagram():
    """{langue: id Instagram} des comptes assignés à l'utilisateur système."""
    ids = {c["username"].lower(): c["id"] for c in liste("me/assigned_instagram_accounts", {"fields": "id,username"})}
    return {langue: ids[nom] for langue, nom in INSTAGRAM.items() if nom in ids}


def jeton_page(page_id):
    return appel("GET", page_id, {"fields": "access_token"})["access_token"]


def legende(titre, description):
    return f"{titre}\n\n{description}".strip()[:LEGENDE_MAX]


def titres_instagram(ig_id):
    """Premières lignes des légendes déjà publiées : le titre de chaque vidéo."""
    return {(m.get("caption") or "").split("\n")[0].strip() for m in liste(f"{ig_id}/media", {"fields": "caption"})}


def titres_facebook(page_id, cle_page):
    return {(r.get("title") or (r.get("description") or "").split("\n")[0]).strip()
            for r in liste(f"{page_id}/video_reels", {"fields": "title,description"}, cle_page)}


def attendre(lire_etat, fini, erreurs, quoi, essais=16, pause=30):
    """Meta traite la vidéo avant publication : on relit l'état toutes les 30 s, 8 min au plus."""
    for _ in range(essais):
        etat = lire_etat()
        if etat in fini:
            return
        if etat in erreurs:
            raise ErreurMeta(f"{quoi} : Meta n'a pas pu traiter la vidéo ({etat})")
        time.sleep(pause)
    raise ErreurMeta(f"{quoi} : vidéo toujours en traitement après {essais * pause // 60} min")


def publier_instagram(ig_id, adresse, titre, description):
    """Publie un Reel à partir de l'adresse publique de la vidéo. Renvoie l'id du média."""
    conteneur = appel("POST", f"{ig_id}/media", {"media_type": "REELS", "video_url": adresse,
                                                  "caption": legende(titre, description), "share_to_feed": "true"})["id"]
    attendre(lambda: appel("GET", conteneur, {"fields": "status_code"}).get("status_code"),
             {"FINISHED"}, {"ERROR", "EXPIRED"}, "Instagram")
    return appel("POST", f"{ig_id}/media_publish", {"creation_id": conteneur})["id"]


def publier_facebook(page_id, cle_page, fichier, titre, description):
    """Publie un Reel sur la Page depuis le fichier (3 à 90 s). Renvoie l'id de la vidéo."""
    debut = appel("POST", f"{page_id}/video_reels", {"upload_phase": "start"}, cle_page)
    contenu = Path(fichier).read_bytes()
    appel("POST", debut["upload_url"], cle=cle_page, corps=contenu,
          entetes={"offset": "0", "file_size": str(len(contenu)), "Content-Type": "application/octet-stream"})
    appel("POST", f"{page_id}/video_reels", {"upload_phase": "finish", "video_id": debut["video_id"],
                                            "video_state": "PUBLISHED", "title": titre,
                                            "description": legende(titre, description)}, cle_page)
    return debut["video_id"]
