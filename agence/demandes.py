"""Demandes de Jules à une équipe : issues ouvertes du dépôt agence avec l'étiquette equipe:<nom>.

Seules les issues écrites par Jules font foi : le filtre est fait par GitHub (creator) puis revérifié ici.
Le texte est rendu tel quel, à traiter comme une demande du conseil, jamais comme du contenu extérieur.
"""
import json
import os
import subprocess

JULES = "sueurhocqjules-droid"
DEPOT = os.environ.get("GITHUB_REPOSITORY", f"{JULES}/agence")
EQUIPES = ["direction", "contenu", "recherche", "operations", "surete", "critique"]


def demandes(equipe):
    """Liste des demandes ouvertes pour l'équipe : numero, titre, texte, lien, date."""
    if equipe not in EQUIPES:
        raise ValueError(f"Équipe inconnue : {equipe!r}")
    brut = subprocess.run(
        ["gh", "api", "-X", "GET", f"repos/{DEPOT}/issues",
         "-f", f"labels=equipe:{equipe}", "-f", "state=open", "-f", f"creator={JULES}", "-f", "per_page=50"],
        capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return [{"numero": i["number"], "titre": i["title"], "texte": i["body"] or "", "lien": i["html_url"],
             "date": i["created_at"]}
            for i in json.loads(brut)
            if i["user"]["login"] == JULES and "pull_request" not in i]


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    for d in demandes(sys.argv[1]):
        print(f"#{d['numero']} {d['titre']} ({d['date'][:10]})")
