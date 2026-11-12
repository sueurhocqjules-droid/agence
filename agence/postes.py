"""Modèle gratuit de chaque poste, choisi au banc d'essai du 10/11 (banc/2026-11-10), avec ses secours dans l'ordre.

Les offres gratuites saturent par moments (Gemini en 503, Groq au quota par minute) : on passe au suivant.
"""
from agence.modeles import appeler

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
}


def demander(poste, consigne):
    """Renvoie (texte, modele, jetons_entree, jetons_sortie, duree_s) du premier modèle qui répond."""
    erreurs = []
    for fournisseur, modele, plafond in POSTES[poste]:
        try:
            texte, entree, sortie, duree = appeler(fournisseur, modele, consigne, plafond)
            return texte, modele, entree, sortie, duree
        except Exception as e:  # noqa: BLE001 : on note et on passe au secours
            erreurs.append(f"{modele} : {str(e)[:120]}")
    raise RuntimeError(f"aucun modèle du poste {poste} n'a répondu ({' ; '.join(erreurs)})")
