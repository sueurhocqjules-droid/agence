"""Copie le moteur de rendu de chaines-studio (privé) vers studio-rendu (dépôt PUBLIC).

    python outils/synchro_rendu.py          # copie, puis montre le diff à commiter dans studio-rendu

Seul ce qui est dans PUBLIC passe. Tout le reste de chaines-studio reste privé :
jetons YouTube (.secrets), publication (publier.py, a_poster.py), nightworks, identité, vidéos rendues, historique Git.
Un fichier supprimé dans chaines-studio est supprimé aussi dans studio-rendu, s'il est dans PUBLIC.
"""
import shutil
import subprocess
import sys
from pathlib import Path

BUREAU = Path(__file__).resolve().parents[2]
SOURCE = BUREAU / "chaines-studio"
CIBLE = BUREAU / "studio-rendu"

PUBLIC = [
    "src/**/*",
    "sujets/*.json",
    "public/sons/*.wav",
    "scripts/calcul_*.py",
    "scripts/rendre.py",
    "scripts/compresser.py",
    "scripts/son.py",
    "scripts/planche.py",
    "package.json",
    "package-lock.json",
    "remotion.config.ts",
    "tsconfig.json",
    "eslint.config.mjs",
]
INTERDIT = (".secrets", "publier", "a_poster", "nightwork", "identite", ".env", "token")


def fichiers(racine):
    return {p.relative_to(racine).as_posix() for motif in PUBLIC for p in racine.glob(motif) if p.is_file()}


def main():
    a_copier = fichiers(SOURCE)
    suspects = [f for f in a_copier if any(mot in f.lower() for mot in INTERDIT)]
    if suspects:
        sys.exit(f"Arrêt : fichiers privés dans la liste publique : {suspects}")
    for chemin in sorted(fichiers(CIBLE) - a_copier):
        (CIBLE / chemin).unlink()
    for chemin in sorted(a_copier):
        (CIBLE / chemin).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE / chemin, CIBLE / chemin)
    print(f"{len(a_copier)} fichiers publics synchronisés")
    subprocess.run(["git", "status", "--short"], cwd=CIBLE)


if __name__ == "__main__":
    main()
