"""Modèle gratuit de chaque poste, choisi au banc d'essai du 10/11 (banc/2026-11-10), avec ses secours dans l'ordre.

Les offres gratuites saturent par moments (Gemini en 503, Groq au quota par minute) : on passe au suivant.
"""
import json
from pathlib import Path

from agence.modeles import appeler

PANNES = Path(__file__).resolve().parent.parent / "registre" / "modeles_en_panne.json"  # écrit par l'Expert en modèles

POSTES = {
    # Le plus proche des traductions validées par Jules ; qwen garde la structure, un peu moins naturel.
    "traduction": [("gemini", "gemini-flash-lite-latest", 4000), ("groq", "qwen/qwen3.8-27b", 4000)],
    # Les trois modèles testés sont justes sur les chiffres ; gpt-oss-120b est le plus rapide.
    "stats": [("groq", "openai/gpt-oss-120b", 4000), ("gemini", "gemini-flash-lite-latest", 4000)],
    # Ordres de grandeur et sources plausibles, mais des erreurs : toute proposition passe par le critique.
    "sujets": [("gemini", "gemini-flash-latest", 9000),
               ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 9000)],
    # Postes de l'étape 7, en attendant le choix de l'Expert en modèles (étape 8) : les modèles justes sur les chiffres
    "critique": [("groq", "openai/gpt-oss-120b", 3000), ("gemini", "gemini-flash-latest", 3000)],
    "programmateur": [("groq", "openai/gpt-oss-120b", 4000), ("gemini", "gemini-flash-latest", 4000)],
    # Gemini resté muet 5 min au premier essai du 12/11 : Groq d'abord
    "chef-contenu": [("groq", "openai/gpt-oss-120b", 6000), ("gemini", "gemini-flash-latest", 6000)],
    # Étape 8 : ~15k jetons de données en entrée, trop pour le quota par minute de Groq : Gemini d'abord
    "chercheur-outils": [("gemini", "gemini-flash-latest", 8000),
                         ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 8000)],
    # Veilleur et Chef de la Recherche : ~3k jetons en entrée, Groq en 4 s ; Gemini en 503 (saturé) à l'essai du 12/11
    "veilleur": [("groq", "openai/gpt-oss-120b", 6000), ("gemini", "gemini-flash-latest", 6000),
                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 6000)],
    "chef-recherche": [("groq", "openai/gpt-oss-120b", 5000), ("gemini", "gemini-flash-latest", 5000),
                       ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 5000)],
    # Chef des opérations : des chiffres à lire justes, peu de données
    "chef-operations": [("groq", "openai/gpt-oss-120b", 3000), ("gemini", "gemini-flash-latest", 3000)],
    # Guetteur (étape 9) : classement court de commentaires en champs fermés, à chaque réveil
    "guetteur": [("groq", "openai/gpt-oss-120b", 3000), ("gemini", "gemini-flash-lite-latest", 3000),
                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 3000)],
    # Courrier (étape 9) : catégorie fermée par mail (objet et extrait), à chaque réveil
    "courrier": [("groq", "openai/gpt-oss-120b", 3000), ("gemini", "gemini-flash-lite-latest", 3000),
                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 3000)],
    # Répondeur : un brouillon court par commentaire ou mail qualifié, en champs fermés, à chaque réveil
    "repondeur": [("groq", "openai/gpt-oss-120b", 4000), ("gemini", "gemini-flash-lite-latest", 4000),
                  ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 4000)],
    # Juge du banc des agents (agence/banc_agents.py) : jamais Claude (MISSION.md, « Décider vite »), réponse fermée
    # oui / non / inconnu. Gemini d'abord, parce que la plupart des agents jugés tournent sur gpt-oss-120b. Flash-Lite en
    # tête : il répond en 1 s quand Flash est saturé (503 après 84 s d'attente le 13/11), et les témoins du banc
    # vérifient à chaque passage qu'il reconnaît les pannes.
    "juge-banc": [("gemini", "gemini-flash-lite-latest", 2000), ("groq", "openai/gpt-oss-120b", 2000),
                  ("gemini", "gemini-flash-latest", 2000), ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 2000)],
    # Étape 12 : Responsable du revenu (peu de données, un choix fermé par chaîne) et Responsable de l'organisation
    # (une ligne de chiffres par poste, ~8k jetons en entrée : Gemini d'abord, le quota par minute de Groq est juste)
    "responsable-revenu": [("groq", "openai/gpt-oss-120b", 4000), ("gemini", "gemini-flash-latest", 4000),
                           ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 4000)],
    "responsable-organisation": [("gemini", "gemini-flash-latest", 5000), ("groq", "openai/gpt-oss-120b", 5000),
                                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 5000)],
    # Gabarits Remotion (agence/gabarits.py) : un JSON de données par sujet, contrôlé par schéma. Mêmes modèles que
    # le poste « sujets » (justes sur les ordres de grandeur), plus Groq en tête pour la vitesse. Jamais Claude.
    "gabarits": [("groq", "openai/gpt-oss-120b", 4000), ("gemini", "gemini-flash-latest", 4000),
                 ("openrouter", "nvidia/nemotron-3-ultra-550b-a55b:free", 4000)],
    # Relecture des PR (agence/relecture.py, règle 9) : jamais Claude, qui écrit les PR de l'Ingénierie. Gemini, dont
    # le quota gratuit par minute tient un diff de 60k caractères ; Groq seulement pour un petit diff.
    "relecteur-pr": [("gemini", "gemini-flash-lite-latest", 3000), ("gemini", "gemini-flash-latest", 3000),
                     ("groq", "openai/gpt-oss-120b", 3000)],
}


def demander(poste, consigne, temperature=None, eviter=None):
    """Renvoie (texte, modele, jetons_entree, jetons_sortie, duree_s) du premier modèle qui répond.
    `eviter` : modèle à n'essayer qu'en dernier (le juge du banc évite le modèle qui a écrit ce qu'il juge)."""
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
