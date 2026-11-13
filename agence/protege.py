"""Fichiers protégés (MISSION.md, règle 9), plan B sur GitHub gratuit : un contrôle qui refuse une PR touchant un fichier
protégé, sauf accord de Jules (étiquette `accord-jules` posée par Jules lui-même).

    python -m agence.protege <numéro de PR>

La protection de branche est refusée sur un dépôt privé en GitHub Free (403) : ce contrôle ne bloque pas le bouton
de fusion, il rend la PR rouge. L'Ingénierie ne fusionne jamais une PR rouge, et ne fusionne jamais seule une PR qui
touche un fichier protégé, même avec l'accord (c'est Jules qui fusionne). Le vrai verrou (règle de branche et
CODEOWNERS obligatoire) viendra avec GitHub Pro (Student Pack).

Le workflow tourne sur `pull_request_target` : le code du contrôle vient de `main`, jamais de la PR. La PR n'est lue
que comme une donnée (liste des fichiers, étiquettes), aucun de ses fichiers n'est exécuté.
"""
import json
import os
import subprocess
import sys

ACCORD = "accord-jules"
JULES = "sueurhocqjules-droid"

# Protégés en entier : toute modification, ajout ou suppression demande l'accord.
# MISSION.md en entier, pas seulement la Gouvernance : la règle 9 couvre aussi la mission et les objectifs, et elle
# vit elle-même dans « Règles de travail ». Le contrôle, la relecture et le moteur du banc sont protégés, sinon une
# PR fusionnée pourrait les assouplir pour la suivante.
TOUJOURS = (
    ".github/",
    "organisation/MISSION.md",
    "organisation/autorisations.toml",   # autorisations clé → postes (guichet, tâche 6)
    "agence/protege.py",
    "agence/relecture.py",
    "agence/banc_agents.py",
)
# Protégés une fois écrits : l'Ingénierie peut ajouter un test ou un cas de banc, jamais en modifier, en retirer ou en
# renommer un (règle 9 : « peut ajouter des tests, jamais en retirer ni en assouplir »).
EXISTANTS = ("tests/", "banc/")


def _sous(chemin, prefixes):
    return any(chemin == p or (p.endswith("/") and chemin.startswith(p)) for p in prefixes)


def raison(chemin, statut, ancien=None):
    """Pourquoi ce changement de fichier demande l'accord de Jules, ou None s'il est libre."""
    for c in filter(None, (chemin, ancien)):
        if _sous(c, TOUJOURS):
            return f"{c} est protégé (règle 9)"
    if statut == "added":
        return None
    for c in filter(None, (ancien, chemin)):
        if _sous(c, EXISTANTS):
            return f"{c} existe déjà : on peut ajouter un test ou un cas, pas le modifier ni le retirer ({statut})"
    return None


def refus(fichiers):
    """fichiers : [(chemin, statut GitHub, ancien chemin ou "")]. Renvoie les raisons, une par fichier protégé touché."""
    return [r for chemin, statut, ancien in fichiers if (r := raison(chemin, statut, ancien))]


def accord(evenements, jules=JULES):
    """evenements : [(labeled|unlabeled, étiquette, auteur)] dans l'ordre. L'accord tient si le dernier geste sur
    l'étiquette `accord-jules` est sa pose par Jules : une étiquette posée par un agent ou un bot ne vaut rien."""
    gestes = [(e, auteur) for e, nom, auteur in evenements if nom == ACCORD]
    return bool(gestes) and gestes[-1] == ("labeled", jules)


def _gh_tsv(chemin, jq):
    sortie = subprocess.run(["gh", "api", "--paginate", chemin, "--jq", jq], capture_output=True, text=True,
                            encoding="utf-8", check=True).stdout
    return [tuple(l.split("\t")) for l in sortie.splitlines() if l.strip()]


def main(args):
    sys.stdout.reconfigure(encoding="utf-8")
    if len(args) != 1 or not args[0].isdigit():
        sys.exit("usage : python -m agence.protege <numéro de PR>")
    pr, depot = args[0], os.environ.get("GITHUB_REPOSITORY", "sueurhocqjules-droid/agence")
    fichiers = _gh_tsv(f"repos/{depot}/pulls/{pr}/files?per_page=100",
                       '.[] | [.filename, .status, (.previous_filename // "")] | @tsv')
    evenements = _gh_tsv(f"repos/{depot}/issues/{pr}/events?per_page=100",
                         '.[] | select(.event == "labeled" or .event == "unlabeled") | [.event, .label.name, .actor.login] | @tsv')
    raisons = refus([(f + ("", ""))[:3] for f in fichiers])
    if not raisons:
        bilan, rouge = f"PR #{pr} : aucun fichier protégé touché ({len(fichiers)} fichier(s))", False
    elif accord(evenements):
        bilan, rouge = f"PR #{pr} : fichiers protégés touchés, accord de Jules donné. Fusion par Jules seulement", False
    else:
        bilan, rouge = (f"PR #{pr} refusée : fichiers protégés touchés sans accord de Jules. Seul Jules peut poser "
                        f"l'étiquette `{ACCORD}` (une étiquette posée par un agent ne compte pas)"), True
    lignes = [bilan, *(f"  - {r}" for r in raisons)]
    print("\n".join(lignes))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write("### Fichiers protégés\n\n" + "\n".join(lignes) + "\n")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"protege={json.dumps(bool(raisons))}\n")
    if rouge:
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
