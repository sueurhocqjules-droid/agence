"""Cohérence des vraies fiches : chaque module nommé existe, chaque équipe est la bonne.  python -m unittest discover tests"""
import importlib.util
import unittest

from agence import organisation


def module_existe(nom):
    try:
        return importlib.util.find_spec(nom) is not None
    except (ImportError, ValueError):
        return False


class CoherenceDesFiches(unittest.TestCase):
    def test_module_de_chaque_fiche_existe(self):
        for id_, fiche in organisation.fiches().items():
            if "module" in fiche:
                self.assertTrue(module_existe(fiche["module"]), f"{id_} : module {fiche['module']!r} introuvable")

    def test_module_de_chaque_script_existe(self):
        for nom, script in organisation.scripts().items():
            self.assertIn("module", script, f"script {nom} : champ module manquant")
            self.assertTrue(module_existe(script["module"]), f"script {nom} : module {script['module']!r} introuvable")

    def test_equipe_a_des_fiches_dont_le_superieur_est_le_chef(self):
        postes = organisation.fiches()
        for chef, fiche in postes.items():
            for membre in fiche.get("equipe", []):
                self.assertIn(membre, postes, f"{chef} cite {membre!r} dans son équipe, qui n'a pas de fiche")
                self.assertEqual(postes[membre].get("superieur"), chef,
                                 f"{membre} est dans l'équipe de {chef}, mais son superieur est {postes[membre].get('superieur')!r}")


if __name__ == "__main__":
    unittest.main()
