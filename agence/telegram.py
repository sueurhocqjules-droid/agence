"""Telegram : le téléphone de Jules, par le bot @Agence_ytb_bot. Aucun modèle, aucun jeton Claude.

Secrets : TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID (secrets du dépôt sur GitHub, agence/.env en local, ignoré par Git).
Seule la conversation de Jules (TELEGRAM_CHAT_ID) reçoit des messages, et seuls ses clics sont lus.
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


def clics(depuis):
    """Clics de Jules sur des boutons depuis l'update `depuis` : (prochain décalage, [(id du clic, donnée, id du message)]).

    Tout ce qui ne vient pas de la conversation de Jules est ignoré. Les updates lues sont confirmées
    à Telegram au prochain appel avec le décalage renvoyé.
    """
    jules, prochain, resultat = chat_jules(), depuis, []
    for update in appeler("getUpdates", {"offset": depuis, "timeout": 0, "allowed_updates": ["callback_query"]}):
        prochain = max(prochain, update["update_id"] + 1)
        clic = update.get("callback_query")
        if not clic or clic["from"]["id"] != jules or clic.get("message", {}).get("chat", {}).get("id") != jules:
            continue
        resultat.append((clic["id"], clic.get("data", ""), clic["message"]["message_id"]))
    return prochain, resultat


def accuser(id_clic, texte):
    appeler("answerCallbackQuery", {"callback_query_id": id_clic, "text": texte[:200]})


def remplacer(id_message, texte):
    """Remplace le texte d'un message (et retire ses boutons), pour que Jules voie que sa réponse est prise."""
    appeler("editMessageText", {"chat_id": chat_jules(), "message_id": id_message, "text": texte[:4096]})
