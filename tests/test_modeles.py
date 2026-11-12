"""Expert en modèles : un modèle en panne passe en dernier, l'ordre du banc est gardé.  python -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import postes


class Pannes(unittest.TestCase):
    def test_modele_en_panne_essaye_en_dernier(self):
        appels = []

        def appeler(fournisseur, modele, consigne, plafond):
            appels.append(modele)
            return "ok", 1, 1, 0.1

        with tempfile.TemporaryDirectory() as d:
            pannes = Path(d) / "pannes.json"
            pannes.write_text(json.dumps({"a": "HTTP 404"}), encoding="utf-8")
            liste = {"essai": [("groq", "a", 10), ("groq", "b", 10), ("groq", "c", 10)]}
            with mock.patch.object(postes, "PANNES", pannes), mock.patch.object(postes, "POSTES", liste), \
                    mock.patch.object(postes, "appeler", appeler):
                self.assertEqual(postes.demander("essai", "x")[1], "b")
                pannes.unlink()
                self.assertEqual(postes.demander("essai", "x")[1], "a")
        self.assertEqual(appels, ["b", "a"])


if __name__ == "__main__":
    unittest.main()
