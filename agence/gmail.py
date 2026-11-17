"""Accès à la boîte mail de boite-chaines (Guetteur, Courrier).

Droits accordés par Jules le 12/11 : lire les mails et gérer les filtres. Rien d'autre :
ni envoi, ni suppression, ni modification d'un mail (règle de deux, propriétés A et B, jamais C).

Jeton : variable d'environnement GMAIL_TOKEN (contenu JSON, secret GitHub),
sinon le fichier local .secrets/token-gmail.json (créé par `python -m agence.gmail connexion`).
Client OAuth : l'appli « Capi Studio » (projet Google capi-studio, en production), API Gmail activée par Jules.
"""
import json
import os
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
LOCAL = RACINE / ".secrets" / "token-gmail.json"
CLIENT = RACINE.parent / "capi-studio" / ".secrets" / "client_secret.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]
COMPTE = os.environ.get("BOITE_CHAINES", "")   # adresse de la boîte des chaînes (.env), hors du dépôt public


def service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    brut = os.environ.get("GMAIL_TOKEN")
    if not brut:
        if not LOCAL.exists():
            raise RuntimeError("Pas de jeton Gmail (GMAIL_TOKEN ou .secrets/token-gmail.json)")
        brut = LOCAL.read_text(encoding="utf-8")
    creds = Credentials.from_authorized_user_info(json.loads(brut.lstrip("﻿")), SCOPES)
    creds.refresh(Request())  # jeton d'accès en mémoire seulement
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def connexion():
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    creds = flow.run_local_server(
        port=0, open_browser=False,
        authorization_prompt_message="Ouvrir ce lien dans le profil Chrome de Capi (boite-chaines) et autoriser :\n{url}",
    )
    adresse = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()["emailAddress"]
    if COMPTE and adresse.lower() != COMPTE.lower():
        sys.exit(f"Mauvais compte autorisé ({adresse}), attendu boite-chaines. Jeton non enregistré.")
    LOCAL.parent.mkdir(exist_ok=True)
    LOCAL.write_text(creds.to_json(), encoding="utf-8")
    print("Connecté à la boîte de boite-chaines. Jeton enregistré dans .secrets/ (hors Git).")


if __name__ == "__main__":
    if sys.argv[1:] != ["connexion"]:
        sys.exit("Usage : python -u -m agence.gmail connexion")
    connexion()
