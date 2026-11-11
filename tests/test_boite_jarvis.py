"""La boîte à outils de Jarvis n'est lue que par le Chercheur d'outils (décidé par Jules le 11/11).  python -m unittest discover tests"""
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
NOM = "boite-a-outils-jarvis"
AUTORISES = {"chercheur-outils.md", "chercheur_outils.py"}


class BoiteJarvis(unittest.TestCase):
    def test_seul_le_chercheur_la_lit(self):
        fichiers = [*(RACINE / "organisation" / "postes").glob("*.md"), *(RACINE / "agents").glob("*.py"),
                    *(RACINE / "agence").glob("*.py"), *(RACINE / "organisation").glob("*.toml")]
        intrus = [f.name for f in fichiers if NOM in f.read_text(encoding="utf-8") and f.name not in AUTORISES]
        self.assertEqual(intrus, [])

    def test_le_chercheur_la_declare(self):
        self.assertIn(NOM, (RACINE / "organisation" / "postes" / "chercheur-outils.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
