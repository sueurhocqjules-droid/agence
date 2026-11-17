import time
import unittest
from datetime import datetime, timezone
from unittest import mock

from agence import questions

QUESTION = {"date": "2026-11-17T00:47:00Z", "id": "1117-0047-1", "par": "ingenierie", "texte": "Je fusionne la PR #99 ?",
            "si_oui": "pause:flux", "si_non": "reprise:flux", "etat": "ouverte", "reponse": "", "message_id": "5"}


class ClicGardeParLeWorker(unittest.TestCase):
    """Demande #46 : les clics viennent du Worker (webhook), chacun n'est appliqué qu'une fois."""

    def relever_deux_fois(self, donnee):
        lignes = [dict(QUESTION)]
        clic = {"update_id": 600000001, "clic_id": "c1", "donnee": donnee, "message_id": 5,
                "envoi": time.time() - 60, "texte": QUESTION["texte"]}
        with mock.patch.object(questions.registre, "lire", side_effect=lambda nom: list(lignes)), \
                mock.patch.object(questions.registre, "ajouter", side_effect=lambda nom, l: lignes.extend(l)), \
                mock.patch.object(questions, "appliquer") as appliquer, \
                mock.patch.object(questions, "telegram") as tg, \
                mock.patch.object(questions, "alarme") as worker:
            worker.clics_recus.return_value = [clic]   # le marquage « lu » s'est perdu : le même clic revient
            prises = [questions.relever(), questions.relever()]
        return prises, appliquer, tg, worker

    def test_un_oui_est_applique_une_seule_fois(self):
        prises, appliquer, tg, worker = self.relever_deux_fois("q:1117-0047-1:oui")
        self.assertEqual(prises, [1, 0])
        appliquer.assert_called_once()
        self.assertEqual(appliquer.call_args.args[0], "pause:flux")
        worker.clics_lus.assert_called_with([600000001])
        textes = [appel.args[1] for appel in tg.remplacer.call_args_list]
        self.assertIn("Ta réponse : OUI. C'est fait", textes[0])
        self.assertIn("déjà prise", textes[1])

    def test_un_non_applique_le_refus(self):
        _, appliquer, _, _ = self.relever_deux_fois("q:1117-0047-1:non")
        self.assertEqual([a.args[0] for a in appliquer.call_args_list], ["reprise:flux"])

    def test_sans_clic_rien_n_est_marque(self):
        with mock.patch.object(questions.registre, "lire", return_value=[]), \
                mock.patch.object(questions, "alarme") as worker:
            worker.clics_recus.return_value = []
            self.assertEqual(questions.relever(), 0)
        worker.clics_lus.assert_not_called()

    def test_plus_aucune_lecture_par_getupdates(self):
        # Un webhook posé rend getUpdates inutilisable (409) : plus rien ne doit l'appeler
        self.assertFalse(hasattr(questions.telegram, "clics"))


class QuestionQuiChangeQuelqueChose(unittest.TestCase):
    def test_oui_et_non_rien_refuse(self):
        with self.assertRaises(ValueError) as e:
            questions.poser("Cette clé ?", "rien", "rien", pourquoi="accès à une clé")

    def test_message_ne_promet_pas_l_heure(self):
        texte = questions.message("Je reprends ?", "raison", "reprise:flux", "rien", "surete", "",
                                  datetime(2026, 11, 11, 21, 30, tzinfo=timezone.utc))
        self.assertIn("quelques heures", texte)
        self.assertIn("prévu", texte)


if __name__ == "__main__":
    unittest.main()
