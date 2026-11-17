"""Accord de Jules sur le code proposé par le Pilote, par un Oui/Non Telegram (question posée par agence/pilote.py).

Le clic est lu par `agence.questions relever`, qui n'accepte que les clics de la conversation de Jules :
  - Oui : la PR est fusionnée avec le jeton de Jules (FUSION_TOKEN), donc en son nom ;
  - Non : la PR est fermée avec un commentaire, le Pilote le voit à sa séance suivante.
Avant de fusionner, la PR est relue : branche `pilote/`, toujours ouverte, aucun fichier interdit (agence/pilote.py).
"""
import json
import os
import subprocess

from agence import guichet

BRANCHE = "pilote/"


def _gh(*args, jeton=None):
    env = {**os.environ, "GH_TOKEN": jeton} if jeton else None
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8", env=env)
    if r.returncode:
        raise RuntimeError(f"gh {' '.join(args[:2])} : {(r.stderr or r.stdout).strip()[:200]}")
    return r.stdout


def _jeton():
    jeton = os.environ.get("FUSION_TOKEN")
    if not jeton:
        raise RuntimeError("clé FUSION_TOKEN absente, fusionne la PR à la main")
    return jeton


def refus_de_fusion(pr):
    """Raison de ne pas fusionner cette PR (dict de `gh pr view --json state,headRefName,files`), ou None."""
    from agence import pilote   # import tardif : pilote importe questions, qui importe ce module
    if pr.get("state") != "OPEN":
        return f"la PR n'est plus ouverte ({pr.get('state')})"
    if not str(pr.get("headRefName", "")).startswith(BRANCHE):
        return f"la PR ne vient pas du Pilote (branche {pr.get('headRefName')})"
    interdits = [f["path"] for f in pr.get("files") or [] if pilote.interdit(f["path"])]
    if interdits:
        return f"elle touche des fichiers interdits : {', '.join(interdits[:5])}"
    return None


def accepter(numero):
    jeton = _jeton()
    pr = json.loads(_gh("pr", "view", str(numero), "-R", guichet.DEPOT, "--json", "state,headRefName,files",
                        jeton=jeton))
    raison = refus_de_fusion(pr)
    if raison:
        raise RuntimeError(f"fusion refusée par le contrôle : {raison}")
    _gh("pr", "merge", str(numero), "-R", guichet.DEPOT, "--squash", "--delete-branch", jeton=jeton)


def refuser(numero):
    jeton = _jeton()
    pr = json.loads(_gh("pr", "view", str(numero), "-R", guichet.DEPOT, "--json", "state,headRefName", jeton=jeton))
    if pr.get("state") != "OPEN" or not str(pr.get("headRefName", "")).startswith(BRANCHE):
        raise RuntimeError(f"fermeture refusée : la PR #{numero} n'est pas une PR ouverte du Pilote")
    _gh("pr", "close", str(numero), "-R", guichet.DEPOT, "--delete-branch", "--comment",
        "Refusée par Jules (Telegram). Le Pilote le voit à sa séance suivante.", jeton=jeton)
