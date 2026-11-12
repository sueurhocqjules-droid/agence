"""Chercheur d'outils : liens tirés des seules données collectées, choix fermés.  python -m unittest discover tests"""
import unittest

from agents.chercheur_outils import liens, normaliser, valider

BON = {"nom": "Outil", "lien": "https://github.com/a/b", "remplace": "auteur", "gratuit": True,
       "pourquoi": "écrit les sujets", "essai": "un sujet de test"}


class Recherche(unittest.TestCase):
    def test_liens_de_la_boite_sans_https(self):
        self.assertEqual(liens("voir github.com/a/b | et https://openrouter.ai/x/y:free."),
                         {"https://github.com/a/b", "https://openrouter.ai/x/y:free"})
        self.assertEqual(normaliser("github.com/a/b/"), "https://github.com/a/b")

    def test_choix_fermes(self):
        autorises, postes = {"https://github.com/a/b"}, {"auteur"}
        cas = {"lien inventé": {**BON, "lien": "https://github.com/x/y"}, "poste inconnu": {**BON, "remplace": "cuisine"},
               "payant": {**BON, "gratuit": False}, "sans essai": {**BON, "essai": " "}}
        for nom, c in cas.items():
            with self.subTest(nom):
                gardes, ecartes = valider({"candidats": [c]}, autorises, postes, set())
                self.assertEqual((len(gardes), len(ecartes)), (0, 1))
        gardes, _ = valider({"candidats": [{**BON, "lien": "github.com/a/b/", "pourquoi": "vite — et bien"}]},
                            autorises, postes, set())
        self.assertEqual((gardes[0]["lien"], gardes[0]["pourquoi"]), ("https://github.com/a/b", "vite, et bien"))

    def test_deja_propose_et_plafond(self):
        _, ecartes = valider({"candidats": [BON]}, {"https://github.com/a/b"}, {"auteur"}, {"https://github.com/a/b"})
        self.assertEqual(ecartes[0]["raison"], "déjà proposé une semaine précédente")
        gardes, _ = valider({"candidats": [BON] * 9}, {"https://github.com/a/b"}, {"auteur"}, set())
        self.assertEqual(len(gardes), 5)

    def test_reponse_illisible(self):
        self.assertEqual(valider({}, set(), set(), set()), ([], []))
        self.assertEqual(valider({"candidats": ["texte"]}, set(), set(), set()), ([], []))


if __name__ == "__main__":
    unittest.main()
