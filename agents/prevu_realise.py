"""Script `prevu_realise` de l'Analyste : écart entre la prévision de chaque achat accordé par Jules et ce que le
registre mesure 4 et 8 semaines après. Lecture seule, n'écrit rien (le bilan du lundi le reprend).

Lancement : python -m agence.lancer prevu_realise
"""
import json
import sys

from agents import analyste


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    lignes, texte = analyste.ecarts()
    for l in lignes:
        print(json.dumps(l, ensure_ascii=False))
    print(texte)


if __name__ == "__main__":
    main()
