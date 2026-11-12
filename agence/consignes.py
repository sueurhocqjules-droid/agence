"""Écriture des fiches par la boucle d'amélioration (organisation/MISSION.md) : retours, changements, annulations.

- Retour : le supérieur écrit trois lignes au plus dans la section « Retours » de la fiche, les 4 derniers sont gardés.
- Changement : le supérieur remplace la section « Consignes » d'une fiche (ou un réglage comme creneaux.toml),
  avec la mesure qu'il doit améliorer, sa valeur avant, la valeur attendue et l'échéance. Un seul en attente
  par poste. C'est un commit Git, et une décision au journal d'audit qui garde l'ancien texte.
- Annulation : à l'échéance, si la mesure ne s'est pas améliorée, le critique remet l'ancien texte (nouveau commit).

Les commits ne se font que si AGENCE_COMMIT=1 (sur GitHub) : en local et dans les tests, les fichiers changent seuls.
"""
import os
import re
import subprocess
from datetime import datetime, timedelta, timezone

from agence import mesures, organisation, registre

RETOURS_GARDES = 4
RACINE = organisation.DOSSIER.parent


def chemin_fiche(poste):
    return organisation.DOSSIER / "postes" / f"{poste}.md"


def _bornes(texte, titre):
    """Début et fin du corps de la section « ## titre » (jusqu'à la section suivante ou la fin)."""
    entete = re.search(rf"^## {re.escape(titre)}[ \t]*\n", texte, re.MULTILINE)
    if not entete:
        raise ValueError(f"Section « {titre} » absente")
    suite = re.search(r"^## ", texte[entete.end():], re.MULTILINE)
    return entete.end(), entete.end() + suite.start() if suite else len(texte)


def lire_section(texte, titre):
    debut, fin = _bornes(texte, titre)
    return texte[debut:fin].strip()


def remplacer_section(texte, titre, corps):
    debut, fin = _bornes(texte, titre)
    apres = "\n" if fin < len(texte) else ""
    return texte[:debut] + corps.strip() + "\n" + apres + texte[fin:]


def commiter(chemins, message):
    if os.environ.get("AGENCE_COMMIT") != "1":
        return
    subprocess.run(["git", "add", *map(str, chemins)], cwd=RACINE, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=RACINE).returncode:
        subprocess.run(["git", "commit", "-q", "-m", message], cwd=RACINE, check=True)


def ajouter_retour(poste, par, texte, jour=None):
    """Écrit un retour (trois lignes au plus, sur une ligne de la fiche) et ne garde que les 4 derniers."""
    lignes = [l.strip() for l in texte.strip().splitlines() if l.strip()]
    if not lignes or len(lignes) > 3:
        raise ValueError(f"Un retour fait de une à trois lignes ({len(lignes)} reçues)")
    chemin = chemin_fiche(poste)
    fiche = chemin.read_text(encoding="utf-8")
    anciens = [l for l in lire_section(fiche, "Retours").splitlines() if l.startswith("- ")]
    jour = jour or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    nouveau = f"- {jour}, {par} : {' / '.join(lignes)}"
    chemin.write_text(remplacer_section(fiche, "Retours", "\n".join((anciens + [nouveau])[-RETOURS_GARDES:])),
                      encoding="utf-8", newline="\n")
    registre.decider(par, f"retour à {poste}", nouveau[2:])
    commiter([chemin], f"Retour de {par} à {poste}")


def en_attente(poste, decisions=None):
    """Le changement de ce poste pas encore jugé par le critique, ou None."""
    return next((d for d in (decisions if decisions is not None else registre.decisions())
                 if d.get("changement", {}).get("poste") == poste and not d["verdict"]), None)


def changer(poste, par, fichier, nouveau, pourquoi, mesure, avant, attendu, jours, section=None):
    """Applique un changement (section d'une fiche, ou fichier entier si section=None) et le note avec sa prédiction.

    `fichier` est relatif à la racine du dépôt. Refuse s'il y a déjà un changement en attente sur ce poste.
    """
    if mesure not in mesures.MESURES:
        raise ValueError(f"Mesure inconnue : {mesure!r}")
    if not isinstance(attendu, (int, float)) or attendu == avant:
        raise ValueError(f"Valeur attendue invalide : {attendu!r} (avant : {avant!r})")
    if not 7 <= jours <= 28:
        raise ValueError(f"Échéance hors de 7 à 28 jours : {jours}")
    if en_attente(poste):
        raise ValueError(f"Un changement est déjà en attente pour {poste} : un seul à la fois")
    chemin = RACINE / fichier
    texte = chemin.read_text(encoding="utf-8")
    ancien = lire_section(texte, section) if section else texte
    if ancien.strip() == nouveau.strip():
        raise ValueError("Rien ne change")
    chemin.write_text(remplacer_section(texte, section, nouveau) if section else nouveau.rstrip() + "\n",
                      encoding="utf-8", newline="\n")
    echeance = (datetime.now(timezone.utc) + timedelta(days=jours)).isoformat(timespec="seconds")
    sens = "monter" if attendu > avant else "baisser"
    ident = registre.decider(
        par, f"changement pour {poste} ({fichier}{', ' + section if section else ''})", pourquoi,
        prediction=f"{mesure} doit {sens} de {avant} à {attendu} d'ici le {echeance[:10]}", mesure=mesure,
        echeance=echeance, avant=avant, attendu=attendu,
        changement={"poste": poste, "fichier": fichier, "section": section, "ancien": ancien, "nouveau": nouveau.strip()})
    commiter([chemin, registre.DOSSIER / "decisions.jsonl"], f"{par} change {fichier} : {pourquoi[:60]}")
    return ident


def annuler(decision, raison):
    """Remet l'ancien texte d'un changement qui n'a rien amélioré, et note l'annulation."""
    c = decision["changement"]
    chemin = RACINE / c["fichier"]
    texte = chemin.read_text(encoding="utf-8")
    actuel = lire_section(texte, c["section"]) if c["section"] else texte
    if actuel.strip() != c["nouveau"].strip():
        registre.decider("critique", f"annulation impossible : {c['fichier']} a changé depuis", raison)
        return False
    chemin.write_text(remplacer_section(texte, c["section"], c["ancien"]) if c["section"] else c["ancien"].rstrip() + "\n",
                      encoding="utf-8", newline="\n")
    registre.decider("critique", f"annulation du changement {decision['id']} ({c['fichier']})", raison)
    commiter([chemin, registre.DOSSIER / "decisions.jsonl"], f"Critique : annulation du changement {decision['id']}")
    return True
