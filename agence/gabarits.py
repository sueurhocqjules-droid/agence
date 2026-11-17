"""Gabarits Remotion des chaînes « Scale of Everything » et « 1 Second vs 1 Hour » (dossier remotion/).

    python -m agence.gabarits <scale-zoom|one-sec-vs-one-hour> "<sujet>" [--voix fr-FR-DeniseNeural] [--sortie out/x.mp4]

Un modèle gratuit (poste « gabarits » de agence/postes.py, ordre choisi avec l'Expert en modèles) écrit un JSON de
données pour le sujet. Le code le contrôle par schéma, fait la voix avec edge-tts, puis rend la vidéo avec Remotion.
Jamais Claude : le coût par sujet est nul, il ne prend rien sur le budget de l'Auteur.
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from agence import modeles, postes

RACINE = Path(__file__).resolve().parent.parent
REMOTION = RACINE / "remotion"
EXEMPLES = REMOTION / "exemples"
MOTS_VOIX_MAX = 75  # ~30 s de voix : au-delà, la vidéo coupe la phrase
COULEUR = re.compile(r"^#[0-9a-fA-F]{6}$")

# gabarit → (identifiant de la composition Remotion, fichier d'exemple)
GABARITS = {
    "scale-zoom": ("ScaleZoom", "scale-zoom.json"),
    "one-sec-vs-one-hour": ("OneSecVsOneHour", "one-sec-vs-one-hour.json"),
}

FORMES = {
    "scale-zoom": '{"titre": "...", "objets": [{"nom": "...", "taille_m": 1.7, "couleur": "#2e86c1"}], "voix": "..."}'
                  " : 4 à 12 objets de tailles différentes (taille_m en mètres, nombre positif), du plus petit au plus grand",
    "one-sec-vs-one-hour": '{"titre": "...", "etats": [{"instant": 0.0, "seconde": "...", "heure": "...", "couleur": "#c0392b"}], "voix": "..."}'
                           " : 3 à 6 états, instant entre 0 et 1 (le premier à 0), seconde = ce qui se passe en 1 s, heure = en 1 h",
}


def _texte(v, maxi=80):
    return isinstance(v, str) and 0 < len(v.strip()) <= maxi


def valider(gabarit, donnees):
    """Liste des erreurs du JSON de données (vide si le schéma est respecté)."""
    if gabarit not in GABARITS:
        return [f"gabarit inconnu : {gabarit}"]
    if not isinstance(donnees, dict):
        return ["les données ne sont pas un objet JSON"]
    erreurs = []
    if not _texte(donnees.get("titre"), 60):
        erreurs.append("titre : texte de 1 à 60 caractères")
    voix = donnees.get("voix")
    if not isinstance(voix, str) or not 0 < len(voix.split()) <= MOTS_VOIX_MAX:
        erreurs.append(f"voix : texte de 1 à {MOTS_VOIX_MAX} mots")
    if gabarit == "scale-zoom":
        objets = donnees.get("objets")
        if not isinstance(objets, list) or not 4 <= len(objets) <= 12:
            return erreurs + ["objets : liste de 4 à 12 objets"]
        for i, o in enumerate(objets):
            if not isinstance(o, dict):
                erreurs.append(f"objets[{i}] : pas un objet")
                continue
            if not _texte(o.get("nom"), 40):
                erreurs.append(f"objets[{i}].nom : texte de 1 à 40 caractères")
            t = o.get("taille_m")
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 < t < 1e30:
                erreurs.append(f"objets[{i}].taille_m : nombre positif")
            if not isinstance(o.get("couleur"), str) or not COULEUR.match(o["couleur"]):
                erreurs.append(f"objets[{i}].couleur : #rrggbb")
        tailles = [o.get("taille_m") for o in objets if isinstance(o, dict) and isinstance(o.get("taille_m"), (int, float))]
        if len(set(tailles)) != len(tailles):
            erreurs.append("objets : deux objets ont la même taille")
    else:
        etats = donnees.get("etats")
        if not isinstance(etats, list) or not 3 <= len(etats) <= 6:
            return erreurs + ["etats : liste de 3 à 6 états"]
        for i, e in enumerate(etats):
            if not isinstance(e, dict):
                erreurs.append(f"etats[{i}] : pas un objet")
                continue
            t = e.get("instant")
            if isinstance(t, bool) or not isinstance(t, (int, float)) or not 0 <= t <= 1:
                erreurs.append(f"etats[{i}].instant : nombre entre 0 et 1")
            for champ in ("seconde", "heure"):
                if not _texte(e.get(champ)):
                    erreurs.append(f"etats[{i}].{champ} : texte de 1 à 80 caractères")
            if not isinstance(e.get("couleur"), str) or not COULEUR.match(e["couleur"]):
                erreurs.append(f"etats[{i}].couleur : #rrggbb")
        instants = [e.get("instant") for e in etats if isinstance(e, dict)]
        if instants and instants[0] != 0:
            erreurs.append("etats[0].instant : doit valoir 0")
    return erreurs


def consigne(gabarit, sujet):
    return ("Tu écris les données d'une vidéo verticale de 30 secondes, en français simple, avec des chiffres justes. "
            f"Sujet : {sujet}\nRéponds par un seul objet JSON, sans texte autour, de cette forme : {FORMES[gabarit]}. "
            f"Le champ voix est le texte lu à voix haute, {MOTS_VOIX_MAX} mots au plus. Pas de tiret long.")


def donnees_du_sujet(gabarit, sujet, demander=None):
    """Demande le JSON au modèle gratuit, le contrôle par schéma. Un second essai avec la liste des erreurs, puis échec."""
    demander = demander or postes.demander
    erreurs = []
    texte = consigne(gabarit, sujet)
    for _ in range(2):
        reponse, *_ = demander("gabarits", texte)
        donnees = modeles.extraire_json(reponse)
        if isinstance(donnees, dict):
            for cle in ("titre", "voix"):
                donnees[cle] = modeles.propre(donnees.get(cle))
        erreurs = valider(gabarit, donnees)
        if not erreurs:
            return donnees
        texte = consigne(gabarit, sujet) + "\nTa réponse précédente était refusée : " + " ; ".join(erreurs[:6])
    raise ValueError("données refusées par le schéma : " + " ; ".join(erreurs[:6]))


def faire_la_voix(texte, mp3, voix="fr-FR-DeniseNeural"):
    subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voix, "--text", texte, "--write-media", str(mp3)],
                   check=True, timeout=300)


def rendre(gabarit, donnees, sortie, avec_voix=True, voix="fr-FR-DeniseNeural"):
    """Rend la vidéo MP4 9:16. La voix, si demandée, est posée dans remotion/public/ le temps du rendu."""
    composition = GABARITS[gabarit][0]
    erreurs = valider(gabarit, donnees)
    if erreurs:
        raise ValueError("données refusées par le schéma : " + " ; ".join(erreurs[:6]))
    donnees = dict(donnees)
    public = REMOTION / "public"
    mp3 = public / f"voix-{gabarit}.mp3"
    if avec_voix:
        public.mkdir(exist_ok=True)
        faire_la_voix(donnees["voix"], mp3, voix)
        donnees["voix"] = mp3.name
    else:
        donnees.pop("voix")
    sortie = Path(sortie).resolve()
    sortie.parent.mkdir(parents=True, exist_ok=True)
    props = REMOTION / "out" / f"props-{gabarit}.json"
    props.parent.mkdir(exist_ok=True)
    props.write_text(json.dumps(donnees, ensure_ascii=False), encoding="utf-8")
    try:
        subprocess.run([shutil.which("npx") or "npx", "remotion", "render", "src/index.ts", composition, str(sortie),
                        f"--props={props}"], cwd=REMOTION, check=True, timeout=900)
    finally:
        mp3.unlink(missing_ok=True)
    return sortie


def main(argv):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(argv) < 2 or argv[0] not in GABARITS:
        print(__doc__)
        return 2
    gabarit, sujet = argv[0], argv[1]
    options = dict(zip(argv[2::2], argv[3::2]))
    donnees = donnees_du_sujet(gabarit, sujet)
    sortie = rendre(gabarit, donnees, options.get("--sortie", f"out/{gabarit}.mp4"),
                    voix=options.get("--voix", "fr-FR-DeniseNeural"))
    print(f"vidéo : {sortie}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
