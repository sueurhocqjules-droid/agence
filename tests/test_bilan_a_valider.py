"""Bilan du lundi : « à valider » lu en direct sur les PR ouvertes.  python -m unittest discover tests"""
import json
import unittest
from datetime import datetime, timezone

from agents import bilan


def faux_github(prs):
    """prs : {numéro: (titre, texte, fichiers [(nom, statut)], état de fusion, événements)}."""
    def gh(*args):
        chemin = args[1] if args[0] == "api" and not args[1].startswith("-") else args[3]
        if chemin.endswith("/pulls"):
            return json.dumps([{"number": n, "title": t, "body": b, "html_url": f"https://github.com/x/pull/{n}"}
                               for n, (t, b, *_) in prs.items()])
        n = int(chemin.split("/")[-2] if chemin.split("/")[-1] in ("files", "events") else chemin.split("/")[-1])
        _, _, fichiers, etat, evenements = prs[n]
        if chemin.endswith("/files"):
            return json.dumps([{"filename": f, "status": s} for f, s in fichiers])
        if chemin.endswith("/events"):
            return json.dumps([{"event": e, "label": {"name": nom}, "actor": {"login": a}} for e, nom, a in evenements])
        return json.dumps({"mergeable_state": etat})
    return gh


class ALValider(unittest.TestCase):
    def test_une_pr_ouverte_qui_touche_un_fichier_protege_apparait(self):
        gh = faux_github({
            39: ("Ajouter un contrôle", "Demande #30 : un contrôle", [(".github/workflows/x.yml", "added")], "clean", []),
            40: ("Petit réglage", "Demande #31 : réglage", [("agents/flux.py", "modified")], "clean", []),
            41: ("Autre réglage", "Demande #32 : autre", [("agents/flux.py", "modified")], "dirty", []),
        })
        prs = bilan.prs_a_valider(gh)
        self.assertEqual([p["numero"] for p in prs], [39, 41])
        self.assertEqual(prs[0]["demande"], 30)
        self.assertIn("en conflit", prs[1]["raisons"])
        texte = bilan.page(datetime(2026, 11, 23, 7, tzinfo=timezone.utc), demandes=[], attente=[], fermees=[],
                           prs=prs)[0]
        a_valider = texte.split(f"## {bilan.ORDRE[0]}")[1].split(f"## {bilan.ORDRE[1]}")[0]
        self.assertIn("[#39](https://github.com/x/pull/39)", a_valider)
        self.assertIn("étiquette `accord-jules` absente", a_valider)
        self.assertIn("issues/30", a_valider)
        self.assertNotIn("#40", a_valider)
        self.assertNotIn("Rien.", a_valider)

    def test_accord_de_jules_donne_la_pr_reste_a_fusionner(self):
        gh = faux_github({7: ("T", "", [("organisation/MISSION.md", "modified")], "clean",
                              [("labeled", "accord-jules", "sueurhocqjules-droid")])})
        self.assertIn("accord donné", bilan.prs_a_valider(gh)[0]["raisons"][0])

    def test_rien_a_valider(self):
        texte = bilan.page(datetime(2026, 11, 23, 7, tzinfo=timezone.utc), demandes=[], attente=[], fermees=[],
                           prs=[])[0]
        self.assertIn("Rien. Tu n'as rien à trancher", texte)


if __name__ == "__main__":
    unittest.main()
