import unittest

from agents import chef_operations


class LigneEntiere(unittest.TestCase):
    def test_ligne_longue_gardee_entiere(self):
        ligne = "Réveils réussis : 92 %. " + "Une panne sans trace sur le courrier, réparée. " * 8
        self.assertLess(300, len(ligne.strip()))
        gardee, *_ = chef_operations.valider({"ligne": ligne}, [])
        self.assertEqual(gardee, ligne.strip())

    def test_ligne_trop_longue_coupee_a_une_fin_de_phrase(self):
        phrase = "Une phrase complète sur les chiffres de la semaine. "
        gardee, *_ = chef_operations.valider({"ligne": phrase * 30}, [])
        self.assertLessEqual(len(gardee), chef_operations.MAX_LIGNE)
        self.assertTrue(gardee.endswith("semaine."))
        self.assertEqual(gardee.count("Une phrase"), len(gardee.split(". ")))

    def test_premiere_phrase_trop_longue_reste_entiere(self):
        longue = "mot " * 200 + "fin. Suite."
        gardee, *_ = chef_operations.valider({"ligne": longue}, [])
        self.assertTrue(gardee.endswith("fin."))


if __name__ == "__main__":
    unittest.main()
