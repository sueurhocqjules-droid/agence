"""Banc d'essai des modèles gratuits sur les vrais postes de l'agence (étape 3 du plan).

    python -m agents.banc [fournisseur:modele ...]

Trois tâches réelles, tirées de chaines-studio et du registre :
  traduction : bloc anglais d'un sujet vers es et pt (référence : la traduction validée de Jules)
  sujets     : 8 nouveaux sujets « What If ... Every Second? » avec paliers chiffrés et sourcés
  stats      : lecture du registre des stats, constats et une recommandation
Contrôles automatiques ci-dessous ; la qualité se juge à la lecture des réponses, rangées dans banc/<date>/.
Local seulement (lit les sujets de ../chaines-studio).
"""
import csv
import json
import re
import sys
from pathlib import Path

from agence import registre
from agence.modeles import appeler, cle, extraire_json

RACINE = Path(__file__).resolve().parents[1]
SUJETS = RACINE.parent / "chaines-studio" / "sujets"
SUJET_TEST = "rice"

MODELES = [
    "groq:openai/gpt-oss-120b",
    "groq:qwen/qwen3.8-27b",
    "groq:openai/gpt-oss-20b",
    "openrouter:nvidia/nemotron-3-ultra-550b-a55b:free",
    "openrouter:google/gemma-4-31b-it:free",
    "gemini:gemini-flash-latest",
    "gemini:gemini-flash-lite-latest",
]


def bloc_anglais():
    sujet = json.loads((SUJETS / f"{SUJET_TEST}.json").read_text(encoding="utf-8"))
    return sujet


def consigne_traduction(sujet, langue):
    nom = {"es": "Spanish (neutral Latin American, understood in Spain)", "pt": "Brazilian Portuguese"}[langue]
    return (
        f"Translate this YouTube Shorts text block from English to {nom}.\n"
        "Rules: return ONLY the JSON object, same keys, same list lengths. Keep every {placeholder} exactly. "
        "Keep UPPERCASE strings in uppercase. On-screen lines must stay short and punchy (they are big captions). "
        "Adapt number words (MILLION, BILLION...) and separators to the target language. "
        "The title must stay a curiosity hook like the English one.\n\n"
        + json.dumps(sujet["en"], ensure_ascii=False, indent=1)
    )


def controle_traduction(source, resultat, reference):
    if not isinstance(resultat, dict):
        return "JSON invalide"
    defauts = []
    if set(resultat) != set(source):
        defauts.append(f"clés {sorted(set(source) ^ set(resultat))}")
    for k, v in source.items():
        r = resultat.get(k)
        if isinstance(v, list) and (not isinstance(r, list) or len(r) != len(v)):
            defauts.append(f"liste {k}")
        if isinstance(v, str):
            if set(re.findall(r"{\w+}", v)) != set(re.findall(r"{\w+}", str(r))):
                defauts.append(f"variables {k}")
            if v.isupper() and isinstance(r, str) and not r.isupper():
                defauts.append(f"majuscules {k}")
    egal_ref = sum(1 for k in source if resultat.get(k) == reference.get(k))
    return (", ".join(defauts) or "ok") + f" | identiques à la réf : {egal_ref}/{len(source)}"


def consigne_sujets():
    tout = registre.lire("stats")
    dernier = max(l["releve"] for l in tout)
    titres = [f"{l['titre']} ({l['vues']} vues)" for l in tout if l["chaine"] == "en" and l["releve"] == dernier]
    return (
        "You write topics for a YouTube Shorts channel. Every video: one thing grows or repeats every second, "
        "and on screen it passes real-world milestones (each milestone = a real, sourced number) until an absurd ending.\n"
        "Existing videos with their views:\n- " + "\n- ".join(titres) + "\n\n"
        "Propose 8 NEW topics (not variants of existing ones). Return ONLY a JSON array of objects: "
        '{"titre": "What If ... Every Second?", "croissance": "x2 or +40% etc.", '
        '"paliers": [{"etape": "...", "chiffre": number, "source": "organisation or paper, year"}] (4 milestones), '
        '"pourquoi": "one sentence on why it would get views"}'
    )


def controle_sujets(resultat):
    if not isinstance(resultat, list):
        return "JSON invalide"
    defauts = []
    for s in resultat:
        t = str(s.get("titre", ""))
        if not (t.startswith("What If") and t.endswith("Every Second?")):
            defauts.append(f"format « {t[:40]} »")
        if len(s.get("paliers", [])) != 4 or not all(p.get("source") for p in s.get("paliers", [])):
            defauts.append(f"paliers « {t[:25]} »")
    return f"{len(resultat)} sujets, " + (", ".join(defauts) or "ok")


def consigne_stats():
    tout = registre.lire("stats")
    dernier = max(l["releve"] for l in tout)
    lignes = [l for l in tout if l["releve"] == dernier]
    entete = "chaine,titre,statut,sortie,vues,likes,commentaires"
    corps = "\n".join(",".join(l[c] for c in entete.split(",")) for l in lignes)
    return (
        "Voici les statistiques YouTube de trois chaînes Shorts (en, es, pt), même format de vidéo traduit. "
        "Réponds en français, 120 mots maximum : 3 constats chiffrés, puis une recommandation concrète pour la semaine. "
        "N'invente aucun chiffre.\n\n" + entete + "\n" + corps
    )


def lancer(cible, nom_tache, consigne, dossier):
    fournisseur, modele = cible.split(":", 1)
    try:  # plafond de sortie par tâche : il compte dans le quota par minute de Groq
        plafond = 9000 if nom_tache == "sujets" else 4000
        texte, entree, sortie, duree = appeler(fournisseur, modele, consigne, plafond)
    except Exception as e:  # noqa: BLE001 : un modèle en panne ne doit pas arrêter le banc
        return None, f"échec : {str(e)[:150]}"
    fichier = dossier / f"{re.sub(r'[^a-z0-9.-]+', '-', modele.lower())}--{nom_tache}.txt"
    fichier.write_text(texte, encoding="utf-8")
    return texte, f"{duree} s, {entree}+{sortie} jetons"


def main(cibles):
    sujet = bloc_anglais()
    dossier = RACINE / "banc" / registre.maintenant()[:10]
    dossier.mkdir(parents=True, exist_ok=True)
    lignes = []
    with registre.seance("banc") as info:
        appels = 0
        for cible in cibles:
            if not cle(cible.split(":")[0]):
                print(f"{cible} : pas de clé, ignoré")
                continue
            for langue in ("es", "pt"):
                texte, mesure = lancer(cible, f"trad-{langue}", consigne_traduction(sujet, langue), dossier)
                note = controle_traduction(sujet["en"], extraire_json(texte or ""), sujet[langue]) if texte else ""
                lignes.append((cible, f"trad-{langue}", mesure, note))
            texte, mesure = lancer(cible, "sujets", consigne_sujets(), dossier)
            lignes.append((cible, "sujets", mesure, controle_sujets(extraire_json(texte or "")) if texte else ""))
            texte, mesure = lancer(cible, "stats", consigne_stats(), dossier)
            lignes.append((cible, "stats", mesure, f"{len((texte or '').split())} mots" if texte else ""))
            appels += 4
            for ligne in lignes[-4:]:
                print(" | ".join(ligne))
        info["appels_gratuits"] = appels
        info["resultat"] = f"ok : {appels} appels, résultats dans banc/{dossier.name}"
    heure = registre.maintenant()[11:16].replace(":", "h")
    with open(dossier / f"resume-{heure}.csv", "w", newline="", encoding="utf-8") as f:
        csv.writer(f, lineterminator="\n").writerows([("modele", "tache", "mesure", "controle"), *lignes])


if __name__ == "__main__":
    main(sys.argv[1:] or MODELES)
