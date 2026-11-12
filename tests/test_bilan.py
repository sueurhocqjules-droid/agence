"""Bilan du lundi : bloc Argent.  python -m unittest discover tests"""
import unittest
from datetime import datetime, timezone

from agents import bilan

DEBUT, FIN = datetime(2026, 11, 9, tzinfo=timezone.utc), datetime(2026, 11, 16, tzinfo=timezone.utc)
SEUILS = {"date": "2026-11-13T00:27:00+00:00",
          "plus_proche": {"chaine": "en", "palier": "yt_fans", "nom": "palier fans", "progression": 0.0029,
                          "critere": "vues_shorts_90j", "valeur": 8576, "cible": 3_000_000,
                          "texte": "Every Second (en) : 8 576 vues Shorts sur 90 jours sur 3 000 000, palier fans"},
          "paliers": [{"chaine": "en", "nom": "palier fans", "progression": 0.0029,
                       "criteres": [{"critere": "abonnes", "valeur": 9, "cible": 500}]},
                      {"chaine": "en", "nom": "partenaire", "progression": 0.0009,
                       "criteres": [{"critere": "abonnes", "valeur": 9, "cible": 1000}]}]}


class Argent(unittest.TestCase):
    def test_seuil_le_plus_proche_et_distance(self):
        texte = "\n".join(bilan.argent(DEBUT, FIN, SEUILS, []))
        self.assertIn("## Argent", texte)
        self.assertIn("8 576 vues Shorts", texte)
        self.assertIn("il manque 2 991 424", texte)
        self.assertIn("0,3 %", texte)
        self.assertIn("du palier « palier fans »", texte)       # le palier le plus avancé de la chaîne seulement
        self.assertNotIn("« partenaire »", texte)
        self.assertIn("Aucune vraie occasion", texte)

    def test_occasions_de_la_periode(self):
        occasions = [{"date": "2026-11-12T10:00:00+00:00", "type": "collaboration", "occasion": True, "chaine": "es",
                      "lien": "https://x/1", "source": "mail"},
                     {"date": "2026-11-01T10:00:00+00:00", "type": "achat", "occasion": True, "chaine": "en",
                      "lien": "https://x/vieux"},
                     {"date": "2026-11-12T11:00:00+00:00", "type": "compliment", "occasion": False, "chaine": "en",
                      "lien": "https://x/2"}]
        texte = "\n".join(bilan.argent(DEBUT, FIN, SEUILS, occasions))
        self.assertIn("collaboration (mail, Cada Segundo (espagnol)) https://x/1", texte)
        self.assertNotIn("x/vieux", texte)
        self.assertIn("1 compliment", texte)

    def test_sans_photo(self):
        self.assertIn("- Seuils : pas encore de photo du Guetteur", bilan.argent(DEBUT, FIN, {}, []))


if __name__ == "__main__":
    unittest.main()
