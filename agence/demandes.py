"""Demandes de Jules à une équipe : issues ouvertes du dépôt agence avec l'étiquette equipe:<nom>.

Seules les issues écrites par Jules font foi : le filtre est fait par GitHub (creator) puis revérifié ici.
Le texte est rendu tel quel, à traiter comme une demande du conseil, jamais comme du contenu extérieur.
"""
import json
import os
import subprocess
import urllib.parse

from agence import registre

JULES = "sueurhocqjules-droid"
DEPOT = os.environ.get("GITHUB_REPOSITORY", f"{JULES}/agence")
EQUIPES = ["direction", "contenu", "recherche", "operations", "surete", "critique"]


PAR_PAGE = 100
PAGES_MAX = 10


def _page(equipe, page):
    """Une page d'issues ouvertes, lue par gh. Le texte de l'erreur de gh remonte, pas seulement son code."""
    requete = urllib.parse.urlencode({"labels": f"equipe:{equipe}", "state": "open", "creator": JULES,
                                      "per_page": PAR_PAGE, "page": page})
    proc = subprocess.run(["gh", "api", f"repos/{DEPOT}/issues?{requete}"],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode:
        raise RuntimeError(f"gh api a échoué (code {proc.returncode}) : {(proc.stderr or proc.stdout).strip()[:200]}")
    rendu = json.loads(proc.stdout or "[]")
    if not isinstance(rendu, list):   # une erreur de l'API (objet « message ») n'est pas une liste vide
        raise RuntimeError(f"gh api a rendu une erreur : {str(rendu.get('message', rendu))[:200]}")
    return rendu


def demandes(equipe):
    """Liste des demandes ouvertes pour l'équipe : numero, titre, texte, lien, date.
    Si la lecture échoue, lève une erreur : une liste vide veut dire « aucune demande », jamais « illisible »."""
    if equipe not in EQUIPES:
        raise ValueError(f"Équipe inconnue : {equipe!r}")
    issues = []
    for page in range(1, PAGES_MAX + 1):
        rendu = _page(equipe, page)
        issues += rendu
        if len(rendu) < PAR_PAGE:
            break
    return [{"numero": i["number"], "titre": i["title"], "texte": i["body"] or "", "lien": i["html_url"],
             "date": i["created_at"]}
            for i in issues
            if i["user"]["login"] == JULES and "pull_request" not in i]


def signaler(equipe, agent, erreur):
    """Lecture ratée : un bloquant au journal de l'agent (la Direction le lit), au lieu d'une liste vide muette."""
    from agence import lancer   # ici seulement : lancer n'a pas besoin de ce module pour démarrer
    lancer.noter_journal(agent, {"date": registre.maintenant(), "quoi": f"demandes-{equipe}", "resultat": "echec",
                                 "bloquant": f"demandes de Jules illisibles (equipe:{equipe}) : {str(erreur)[:200]}"})


def illisibles():
    """Équipes dont la lecture échoue maintenant : [(équipe, erreur)]. Pour le récapitulatif Telegram."""
    pannes = []
    for equipe in EQUIPES:
        try:
            demandes(equipe)
        except Exception as e:  # noqa: BLE001 : on les dit toutes
            pannes.append((equipe, str(e)[:120]))
    return pannes


def repondre(numero, texte):
    """Répond dans l'issue puis la ferme : la demande est traitée, Jules la rouvre s'il veut aller plus loin."""
    if os.environ.get("AGENCE_ESSAI") == "1":
        print(f"ESSAI : réponse à l'issue #{numero} non envoyée :", texte)
        return
    subprocess.run(["gh", "issue", "comment", str(numero), "-R", DEPOT, "--body-file", "-"],
                   input=texte, text=True, encoding="utf-8", check=True, capture_output=True)
    subprocess.run(["gh", "issue", "close", str(numero), "-R", DEPOT], check=True, capture_output=True)


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for d in demandes(sys.argv[1]):
        print(f"#{d['numero']} {d['titre']} ({d['date'][:10]})")
