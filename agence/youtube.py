"""Accès à l'API YouTube des chaînes de l'agence.

Jeton de chaque chaîne : variable d'environnement YT_TOKEN_<LANGUE> (contenu JSON, secret GitHub),
sinon le fichier local de chaines-studio (même jeton, créé par `publier.py connexion`).
L'appli OAuth « Capi Studio » est en production : le jeton de rafraîchissement n'expire pas.
"""
import json
import os
from pathlib import Path

CHAINES = {
    "en": ("Every Second", "UCiuTySJ8_2u6VEuJSM7ED8Q"),
    "es": ("Cada Segundo", "UC97Z7OSAvbR3Gr4U-jjiZYg"),
    "pt": ("A Cada Segundo", "UCF3-d1rpT4WvXYF3a0qJvVg"),
}
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
LOCAL = Path(__file__).resolve().parents[2] / "chaines-studio" / ".secrets"


def client(langue):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    brut = os.environ.get(f"YT_TOKEN_{langue.upper()}")
    if not brut:
        fichier = LOCAL / f"token-{langue}.json"
        if not fichier.exists():
            raise RuntimeError(f"Pas de jeton YouTube pour {langue} (YT_TOKEN_{langue.upper()} ou {fichier})")
        brut = fichier.read_text(encoding="utf-8")
    creds = Credentials.from_authorized_user_info(json.loads(brut.lstrip("﻿")), SCOPES)  # BOM ajouté par PowerShell 5
    creds.refresh(Request())  # jeton d'accès en mémoire seulement, rien n'est réécrit
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def videos(youtube, parties="snippet,status,statistics"):
    """Toutes les vidéos de la chaîne connectée, privées et programmées comprises."""
    chaine = youtube.channels().list(part="contentDetails", mine=True).execute()
    envois = chaine["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        reponse = youtube.playlistItems().list(part="contentDetails", playlistId=envois,
                                               maxResults=50, pageToken=page).execute()
        ids += [item["contentDetails"]["videoId"] for item in reponse["items"]]
        page = reponse.get("nextPageToken")
        if not page:
            break
    resultat = []
    for i in range(0, len(ids), 50):
        resultat += youtube.videos().list(part=parties, id=",".join(ids[i:i + 50])).execute()["items"]
    return resultat
