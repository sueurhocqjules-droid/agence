"""Lecture de l'organisation : fiches de poste (organisation/postes/*.md, en-tête TOML entre +++) et scripts."""
import tomllib
from pathlib import Path

DOSSIER = Path(__file__).resolve().parent.parent / "organisation"
SOMMET = "jules"


def fiches():
    """Toutes les fiches de poste, par identifiant."""
    resultat = {}
    for chemin in sorted((DOSSIER / "postes").glob("*.md")):
        morceaux = chemin.read_text(encoding="utf-8").split("+++")
        if len(morceaux) < 3:
            raise ValueError(f"{chemin.name} : en-tête +++ manquant")
        fiche = tomllib.loads(morceaux[1])
        resultat[fiche["id"]] = fiche
    return resultat


def scripts():
    """Les scripts, par nom, avec leur agent propriétaire."""
    with open(DOSSIER / "scripts.toml", "rb") as f:
        return tomllib.load(f)


def chaine_de_commandement(agent, postes):
    """L'agent puis ses supérieurs successifs, jusqu'à Jules exclu."""
    chaine = []
    while agent != SOMMET:
        if agent in chaine or agent not in postes:
            raise ValueError(f"Hiérarchie invalide autour de {agent!r}")
        chaine.append(agent)
        agent = postes[agent]["superieur"]
    return chaine
