"""Ligne d'appel vers la boutique ([boutique] de diffusion.toml) en tête des descriptions.  python -m unittest discover tests"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents import flux

CALCUL = {"descriptions": {"en": "Every second, 1 000 sheets.", "pt": "A cada segundo, 1 000 folhas."}}


def reglage(texte):
    dossier = tempfile.mkdtemp()
    chemin = Path(dossier) / "diffusion.toml"
    chemin.write_text(texte, encoding="utf-8")
    return chemin


class AppelBoutique(unittest.TestCase):
    def test_lien_vide_rien_n_est_ajoute(self):
        chemin = reglage('[boutique]\nlien = ""\nen = "Posters: {lien}"\n')
        self.assertEqual(flux.appel_boutique("en", chemin), "")

    def test_lien_https_mis_dans_le_texte(self):
        chemin = reglage('[boutique]\nlien = "https://ko-fi.com/everysecond"\nen = "Posters: {lien}"\n')
        self.assertEqual(flux.appel_boutique("en", chemin), "Posters: https://ko-fi.com/everysecond")

    def test_refus_http_texte_sans_lien_langue_absente_trop_long(self):
        self.assertEqual(flux.appel_boutique("en", reglage('[boutique]\nlien = "http://x.com"\nen = "{lien}"\n')), "")
        self.assertEqual(flux.appel_boutique("en", reglage('[boutique]\nlien = "https://x.com"\nen = "Posters"\n')), "")
        self.assertEqual(flux.appel_boutique("es", reglage('[boutique]\nlien = "https://x.com"\nen = "{lien}"\n')), "")
        long = "a" * 200
        self.assertEqual(flux.appel_boutique("en", reglage(f'[boutique]\nlien = "https://x.com"\nen = "{long} {{lien}}"\n')), "")

    def test_reglage_illisible_ou_absent(self):
        self.assertEqual(flux.appel_boutique("en", reglage("[boutique\n")), "")
        self.assertEqual(flux.appel_boutique("en", reglage("[instagram]\npar_jour = 3\n")), "")
        self.assertEqual(flux.appel_boutique("en", Path(tempfile.mkdtemp()) / "absent.toml"), "")

    def test_description_avec_et_sans_appel(self):
        with mock.patch.object(flux, "appel_boutique", return_value="Posters: https://ko-fi.com/x"):
            self.assertEqual(flux.description(CALCUL, "en"), "Posters: https://ko-fi.com/x\n\nEvery second, 1 000 sheets.")
        with mock.patch.object(flux, "appel_boutique", return_value=""):
            self.assertEqual(flux.description(CALCUL, "pt"), "A cada segundo, 1 000 folhas.")

    def test_reglage_du_depot_lisible(self):
        """Le vrai diffusion.toml se lit, et sa section boutique ne compte pas comme un réseau qui diffuse."""
        self.assertIsInstance(flux.appel_boutique("en"), str)
        self.assertEqual(flux.cadence_diffusion().get("boutique", 0), 0)


if __name__ == "__main__":
    unittest.main()
