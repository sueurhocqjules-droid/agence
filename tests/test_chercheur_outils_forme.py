"""Le Chercheur d'outils ne casse pas quand le modèle répond par une liste (demande #94)."""
import unittest

from agents import chercheur_outils


class FormeReponseTest(unittest.TestCase):
    def test_objet_inchange(self):
        self.assertEqual(chercheur_outils.forme_reponse({"candidats": []}), {"candidats": []})

    def test_liste_lue_comme_candidats(self):
        r = chercheur_outils.forme_reponse([{"nom": "x"}])
        self.assertEqual(r, {"candidats": [{"nom": "x"}]})
        gardes, ecartes = chercheur_outils.valider(r, set(), set(), set())
        self.assertEqual(gardes, [])
        self.assertEqual(len(ecartes), 1)

    def test_autre_forme_rejetee(self):
        self.assertEqual(chercheur_outils.forme_reponse("texte"), {})
        self.assertEqual(chercheur_outils.forme_reponse(None), {})


if __name__ == "__main__":
    unittest.main()
