import unittest
from datetime import datetime, timezone

from agence import questions


class QuestionQuiChangeQuelqueChose(unittest.TestCase):
    def test_oui_et_non_rien_refuse(self):
        with self.assertRaises(ValueError) as e:
            questions.poser("Cette clé ?", "rien", "rien", pourquoi="accès à une clé")
        self.assertIn("accord-jules", str(e.exception))

    def test_message_ne_promet_pas_l_heure(self):
        texte = questions.message("Je reprends ?", "raison", "reprise:flux", "rien", "surete", "",
                                  datetime(2026, 11, 11, 21, 30, tzinfo=timezone.utc))
        self.assertIn("quelques heures", texte)
        self.assertIn("prévu", texte)


if __name__ == "__main__":
    unittest.main()
