"""Écriture des sujets par un modèle gratuit (Ling 3.2 Flash, puis gpt-oss-120b), à la place de Claude.

    python -m agence.lancer sujets "<idée de règle absurde>" ["<autre idée>" ...]

Propriétaire : le Programmateur (le coût d'un sujet limite la cadence, besoin « sujets » du registre).
Pour chaque idée, un modèle (poste « ecrire-sujets » de agence/postes.py, jamais Claude) rend un JSON : le sujet
(titre en, es, pt) et son calcul chiffré (descriptions par langue, étapes). Le code le contrôle, puis l'écrit sur la
sortie standard, un objet JSON par ligne : {"sujet": {...}, "calcul": {...}}. Ce sont les deux fichiers que
chaines-studio et `agents/flux.py` lisent (`<sujet>.json` et `<sujet>.calcul.json`). L'Auteur ne fait plus que
relire ces sujets et écrire le code Remotion.
Le journal du lanceur note : sujets écrits, sujets acceptés.
"""
import json
import sys

from agence import modeles, postes, registre

LANGUES = ("en", "es", "pt")
ETAPES = (3, 8)         # nombre d'étapes du calcul
TITRE_MAX = 100         # limite des titres YouTube
DESCRIPTION_MAX = 1000

FORME = ('{"sujet": {"en": {"titre": "..."}, "es": {"titre": "..."}, "pt": {"titre": "..."}}, '
         '"calcul": {"regle": "...", "resultat": "...", "etapes": [{"texte": "...", "valeur": 0.0, "unite": "..."}], '
         '"descriptions": {"en": "...", "es": "...", "pt": "..."}}}')


def _texte(v, maxi):
    return isinstance(v, str) and 0 < len(v.strip()) <= maxi


def valider(donnees):
    """Liste des erreurs du JSON d'un sujet (vide si le format est respecté)."""
    if not isinstance(donnees, dict):
        return ["la réponse n'est pas un objet JSON"]
    erreurs = []
    sujet, calcul = donnees.get("sujet"), donnees.get("calcul")
    if not isinstance(sujet, dict):
        erreurs.append("sujet : objet avec une entrée par langue")
    else:
        for l in LANGUES:
            if not isinstance(sujet.get(l), dict) or not _texte(sujet[l].get("titre"), TITRE_MAX):
                erreurs.append(f"sujet.{l}.titre : texte de 1 à {TITRE_MAX} caractères")
    if not isinstance(calcul, dict):
        return erreurs + ["calcul : objet"]
    for champ in ("regle", "resultat"):
        if not _texte(calcul.get(champ), 300):
            erreurs.append(f"calcul.{champ} : texte de 1 à 300 caractères")
    descriptions = calcul.get("descriptions")
    for l in LANGUES:
        if not isinstance(descriptions, dict) or not _texte(descriptions.get(l), DESCRIPTION_MAX):
            erreurs.append(f"calcul.descriptions.{l} : texte de 1 à {DESCRIPTION_MAX} caractères")
    etapes = calcul.get("etapes")
    if not isinstance(etapes, list) or not ETAPES[0] <= len(etapes) <= ETAPES[1]:
        return erreurs + [f"calcul.etapes : liste de {ETAPES[0]} à {ETAPES[1]} étapes"]
    for i, e in enumerate(etapes):
        if not isinstance(e, dict):
            erreurs.append(f"calcul.etapes[{i}] : pas un objet")
            continue
        if not _texte(e.get("texte"), 200):
            erreurs.append(f"calcul.etapes[{i}].texte : texte de 1 à 200 caractères")
        v = e.get("valeur")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            erreurs.append(f"calcul.etapes[{i}].valeur : nombre")
        if not _texte(e.get("unite"), 30):
            erreurs.append(f"calcul.etapes[{i}].unite : texte de 1 à 30 caractères")
    return erreurs


def consigne(idee):
    return f"""Tu écris un sujet pour trois chaînes de vidéos courtes « Every Second » (YouTube Shorts, en, es, pt) :
une règle absurde appliquée chaque seconde (« What If … Every Second? »), avec un vrai calcul chiffré et des étapes
vérifiables (ordres de grandeur justes, aucune valeur inventée sans le dire).
Idée : {idee}
Titres naturels dans chaque langue, pas de traduction mot à mot. Ni tiret long, ni émoji.
Réponds seulement en JSON, de cette forme : {FORME}
Le calcul compte de {ETAPES[0]} à {ETAPES[1]} étapes."""


def ecrire(idee):
    """Renvoie (donnees, modele) ou lève ValueError (message : ce qui ne va pas). Le poste essaie Ling, puis gpt-oss-120b."""
    texte, modele, *_ = postes.demander("ecrire-sujets", consigne(idee))
    donnees = modeles.extraire_json(texte)
    erreurs = valider(donnees)
    if erreurs:
        raise ValueError(f"{modele} : " + " ; ".join(erreurs[:3]))
    return donnees, modele


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    idees = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not idees:
        sys.exit('usage : python -m agence.lancer sujets "<idée>" ["<autre idée>" ...]')
    with registre.seance("sujets") as info:
        ecrits = acceptes = 0
        for idee in idees:
            try:
                donnees, modele = ecrire(idee)
            except RuntimeError as e:     # aucun modèle n'a répondu
                print(f"pas de réponse : {e}", file=sys.stderr)
                continue
            except ValueError as e:       # répondu, mais hors format
                ecrits += 1
                print(f"refusé : {e}", file=sys.stderr)
                continue
            ecrits += 1
            acceptes += 1
            info["appels_gratuits"] += 1
            print(json.dumps(donnees, ensure_ascii=False))
        info["appels_gratuits"] = max(info["appels_gratuits"], ecrits)
        info["resultat"] = f"ok : {ecrits} sujets écrits, {acceptes} acceptés"
        print(info["resultat"], file=sys.stderr)


if __name__ == "__main__":
    main()
