"""Telegram : le téléphone de Jules, par le bot @Agence_ytb_bot. Aucun modèle, aucun jeton Claude.

Secrets : TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID (secrets du dépôt sur GitHub, agence/.env en local, ignoré par Git).
Seule la conversation de Jules (TELEGRAM_CHAT_ID) reçoit des messages. Ses clics sur les boutons arrivent au Worker
de l'alarme par webhook (alarme/worker.js) : getUpdates ne marche plus une fois le webhook posé, et un clic non lu y
disparaissait en 2 à 3 minutes.
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

LOCAL = Path(__file__).resolve().parents[1] / ".env"


def _reglage(nom):
    valeur = os.environ.get(nom)
    if not valeur and LOCAL.exists():
        for ligne in LOCAL.read_text(encoding="utf-8-sig").splitlines():
            if ligne.startswith(f"{nom}="):
                valeur = ligne.split("=", 1)[1].strip()
    if not valeur:
        raise RuntimeError(f"{nom} manquant (secret du dépôt, ou {LOCAL} en local)")
    return valeur


def chat_jules():
    return int(_reglage("TELEGRAM_CHAT_ID"))


def appeler(methode, donnees, delai=30):
    requete = urllib.request.Request(f"https://api.telegram.org/bot{_reglage('TELEGRAM_BOT_TOKEN')}/{methode}",
                                     data=json.dumps(donnees).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(requete, timeout=delai) as reponse:
            resultat = json.load(reponse)
    except urllib.error.HTTPError as e:  # le message d'erreur de Telegram, jamais l'adresse (elle contient le jeton)
        raise RuntimeError(f"Telegram {methode} : {e.code} {e.read()[:200]!r}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Telegram {methode} injoignable : {e.reason}") from None
    if not resultat.get("ok"):
        raise RuntimeError(f"Telegram {methode} : {resultat.get('description')}")
    return resultat["result"]


def envoyer(texte, boutons=None):
    """Envoie un message en texte brut à Jules. boutons : [(libellé, donnée)], sur une ligne. Renvoie l'id du message."""
    donnees = {"chat_id": chat_jules(), "text": texte[:4096], "disable_web_page_preview": True}
    if boutons:
        donnees["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in boutons]]}
    return appeler("sendMessage", donnees)["message_id"]


def remplacer(id_message, texte):
    """Remplace le texte d'un message (et retire ses boutons), pour que Jules voie que sa réponse est prise."""
    appeler("editMessageText", {"chat_id": chat_jules(), "message_id": id_message, "text": texte[:4096]})
