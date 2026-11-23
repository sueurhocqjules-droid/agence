"""Modèle gratuit de chaque poste, avec ses secours dans l'ordre.

Les offres gratuites saturent par moments (Gemini en 503, Groq au quota par minute) : on passe au suivant.
"""
import json
from pathlib import Path

from agence.modeles import appeler

PANNES = Path(__file__).resolve().parent.parent / "registre" / "modeles_en_panne.json"  # un modèle noté ici passe en dernier

POSTES = {
    # Courrier et Guetteur : catégorie fermée par mail ou commentaire, à chaque réveil
    "courrier": [("groq", "openai/gpt-oss-120b", 3000), ("gemini", "gemini-flash-lite-latest", 3000),
                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 3000)],
    "guetteur": [("groq", "openai/gpt-oss-120b", 3000), ("gemini", "gemini-flash-lite-latest", 3000),
                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 3000)],
    # Gabarits Remotion (agence/gabarits.py) : un JSON de données par sujet, contrôlé par schéma. Jamais Claude.
    "gabarits": [("groq", "openai/gpt-oss-120b", 4000), ("gemini", "gemini-flash-latest", 4000),
                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 4000)],
}


def demander(poste, consigne, temperature=None, eviter=None):
    """Renvoie (texte, modele, jetons_entree, jetons_sortie, duree_s) du premier modèle qui répond.
    `eviter` : modèle à n'essayer qu'en dernier."""
    erreurs = []
    pannes = json.loads(PANNES.read_text(encoding="utf-8")) if PANNES.exists() else {}
    for fournisseur, modele, plafond in sorted(POSTES[poste], key=lambda m: (m[1] in pannes, m[1] == eviter)):  # tri stable
        try:
            reglage = {} if temperature is None else {"temperature": temperature}
            texte, entree, sortie, duree = appeler(fournisseur, modele, consigne, plafond, **reglage)
            return texte, modele, entree, sortie, duree
        except Exception as e:  # noqa: BLE001 : on note et on passe au secours
            erreurs.append(f"{modele} : {str(e)[:120]}")
    raise RuntimeError(f"aucun modèle du poste {poste} n'a répondu ({' ; '.join(erreurs)})")
