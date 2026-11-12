"""Appel des modèles gratuits (Groq, OpenRouter, Gemini), tous par l'API compatible OpenAI.

Clé de chaque fournisseur : variable d'environnement (secret GitHub), sinon le .env local de Jarvis.
Aucune dépendance : urllib suffit.
"""
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

FOURNISSEURS = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY"),
}
ENV_LOCAL = Path(__file__).resolve().parents[2] / "jarvis-starter-kit" / ".env"


def cle(fournisseur):
    nom = FOURNISSEURS[fournisseur][1]
    if os.environ.get(nom):
        return os.environ[nom]
    if ENV_LOCAL.exists():
        for ligne in ENV_LOCAL.read_text(encoding="utf-8-sig").splitlines():
            if ligne.startswith(nom + "="):
                return ligne.split("=", 1)[1].strip().strip('"') or None
    return None


def appeler(fournisseur, modele, consigne, max_tokens=12000):
    """Renvoie (texte, jetons_entree, jetons_sortie, duree_s). Lève RuntimeError avec le message de l'API."""
    base, _ = FOURNISSEURS[fournisseur]
    corps = json.dumps({
        "model": modele,
        "messages": [{"role": "user", "content": consigne}],
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()
    requete = urllib.request.Request(f"{base}/chat/completions", data=corps, headers={
        "Authorization": f"Bearer {cle(fournisseur)}",
        "Content-Type": "application/json",
        "User-Agent": "agence",
    })
    debut = time.monotonic()
    for essai in range(3):
        try:
            with urllib.request.urlopen(requete, timeout=300) as r:
                reponse = json.load(r)
            break
        except urllib.error.HTTPError as e:
            message = e.read().decode(errors="replace")[:500]
            if e.code not in (429, 503) or "too large" in message or essai == 2:
                raise RuntimeError(f"HTTP {e.code} : {message}") from None
            attente = float(e.headers.get("retry-after") or 0) or 30  # quota par minute des offres gratuites
            time.sleep(min(attente + 1, 70))
    duree = round(time.monotonic() - debut, 1)
    usage = reponse.get("usage") or {}
    texte = reponse["choices"][0]["message"].get("content") or ""
    return texte, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0), duree


def propre(valeur):
    """Les modèles mettent des tirets longs malgré la consigne : virgule à la place (règle de Jules)."""
    return valeur.replace(" — ", ", ").replace("—", ", ") if isinstance(valeur, str) else valeur


def extraire_json(texte):
    """Premier objet ou tableau JSON du texte (les modèles l'entourent souvent de ```json)."""
    for ouvrant, fermant in (("{", "}"), ("[", "]")):
        i, j = texte.find(ouvrant), texte.rfind(fermant)
        if i != -1 and j > i:
            try:
                return json.loads(texte[i:j + 1])
            except json.JSONDecodeError:
                continue
    return None
