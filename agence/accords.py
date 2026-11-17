"""Accord de Jules sur une PR qui touche un fichier protégé, par un Oui/Non Telegram.

    python -m agence.lancer accords        (script `accords`, à chaque réveil)

Pour chaque PR ouverte qui touche un fichier protégé (agence/protege.py) sans accord de Jules, une seule question
Telegram. Le clic est lu par `agence.questions relever`, qui n'accepte que les clics de la conversation de Jules :
  - Oui : l'étiquette `accord-jules` est posée puis la PR fusionnée avec le jeton de Jules (FUSION_TOKEN), donc en
    son nom : le contrôle des fichiers protégés la reconnaît comme la sienne ;
  - Non : la PR est fermée avec un commentaire, l'agence reprend la demande autrement.
Une question dont la PR a été fusionnée ou fermée entre-temps est close, et Jules le voit sur le message.
"""
import json
import os
import subprocess
import sys

from agence import protege, questions, registre

DEPOT = os.environ.get("GITHUB_REPOSITORY", "sueurhocqjules-droid/agence")
PAR = "ingenierie"


def _gh(*args, jeton=None):
    env = {**os.environ, "GH_TOKEN": jeton} if jeton else None
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} : {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout


def _jeton():
    jeton = os.environ.get("FUSION_TOKEN")
    if not jeton:
        raise RuntimeError("clé FUSION_TOKEN absente, pose l'étiquette accord-jules et fusionne à la main")
    return jeton


def accepter(pr):
    jeton = _jeton()
    _gh("pr", "edit", pr, "-R", DEPOT, "--add-label", protege.ACCORD, jeton=jeton)
    _gh("pr", "merge", pr, "-R", DEPOT, "--squash", "--delete-branch", jeton=jeton)


def refuser(pr):
    _gh("pr", "close", pr, "-R", DEPOT, "--comment",
        "Refusée par Jules (Telegram). L'Ingénierie reprend la demande autrement, sans ce changement de fichier protégé.",
        jeton=_jeton())


def controles(rollup):
    """Les contrôles d'une PR en une ligne, pour aider Jules à choisir."""
    etats = [f"{c.get('name') or c.get('context')} {c.get('conclusion') or c.get('state') or c.get('status')}".lower()
             for c in rollup]
    return "Contrôles : " + (", ".join(etats) if etats else "aucun pour l'instant")


def a_demander(prs, deja, raisons_de, accord_de):
    """PR à soumettre à Jules : ouvertes, fichiers protégés touchés, sans accord ni question déjà posée.
    Renvoie [(pr, raisons)]."""
    resultat = []
    for pr in prs:
        n = pr["number"]
        if f"accord:{n}" in deja:
            continue
        raisons = raisons_de(n)
        if raisons and not accord_de(n):
            resultat.append((pr, raisons))
    return resultat


def demander():
    prs = json.loads(_gh("pr", "list", "-R", DEPOT, "--state", "open", "--limit", "100",
                         "--json", "number,title,url,statusCheckRollup"))
    etat = questions.etat_questions(registre.lire("questions"))
    ouvertes = {str(p["number"]) for p in prs}
    for q in etat.values():
        if q["etat"] == "ouverte" and q["si_oui"].startswith("accord:") and q["si_oui"][7:] not in ouvertes:
            questions.clore(q["si_oui"], "la PR a été fusionnée ou fermée entre-temps")
    deja = {q["si_oui"] for q in etat.values() if q["etat"] != "close"}

    def raisons_de(n):
        fichiers = protege._gh_tsv(f"repos/{DEPOT}/pulls/{n}/files?per_page=100",
                                   '.[] | [.filename, .status, (.previous_filename // "")] | @tsv')
        return protege.refus([(f + ("", ""))[:3] for f in fichiers])

    def accord_de(n):
        return protege.accord(protege._gh_tsv(
            f"repos/{DEPOT}/issues/{n}/events?per_page=100",
            '.[] | select(.event == "labeled" or .event == "unlabeled") | [.event, .label.name, .actor.login] | @tsv'))

    posees = 0
    for pr, raisons in a_demander(prs, deja, raisons_de, accord_de):
        n = pr["number"]
        questions.poser(f"Je fusionne la PR #{n} « {pr['title']} » ? {pr['url']}", f"accord:{n}", f"refus:{n}",
                        par=PAR, pourquoi="Elle touche des fichiers protégés : " + " ; ".join(raisons[:5]),
                        conseil=controles(pr.get("statusCheckRollup") or []))
        posees += 1
    print(f"{posees} PR soumise(s) à Jules sur Telegram")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    demander()
