"""Tests de l'étape 6 : compteur, seuils, sanctions, pannes, questions à choix fermés python -m unittest discover tests"""
import json
import tempfile
import time
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

from agence import lancer, organisation, questions
from agents import surete

REGLAGES = {"claude": {"dollars_par_pourcent": 0, "limite_pourcent": 20}}
MERCREDI = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)
LUNDI_MATIN = datetime(2026, 11, 16, 7, tzinfo=timezone.utc)


def cout(agent, quand, dollars=0, appels=0):
    return {"agent": agent, "debut": quand, "dollars_equiv": str(dollars), "appels_gratuits": str(appels)}


class Compteur(unittest.TestCase):
    def test_semaine_en_cours_seulement(self):
        couts = [cout("auteur", "2026-11-06T22:00:00+00:00", 50), cout("auteur", "2026-11-10T02:00:00+00:00", 14.2),
                 cout("banc", "2026-11-10T21:00:00+00:00", 0, 4)]
        c = surete.compteur(MERCREDI, couts, None, REGLAGES)
        self.assertAlmostEqual(c["dollars"], 14.2)
        self.assertEqual(c["appels"], 4)
        self.assertIsNone(c["pourcent"])
        self.assertFalse(c["atelier_lu"])

    def test_atelier_ajoute_et_etalon(self):
        atelier = [cout("auteur", "2026-11-11T12:43:12Z", 10)]
        c = surete.compteur(MERCREDI, [cout("direction", "2026-11-11T08:00:00+00:00", 5)], atelier,
                            {"claude": {"dollars_par_pourcent": 2.5}})
        self.assertAlmostEqual(c["dollars"], 15)
        self.assertAlmostEqual(c["pourcent"], 6)

    def test_fin_exclut_la_semaine_suivante(self):
        couts = [cout("auteur", "2026-11-14T00:00:00+00:00", 3), cout("auteur", "2026-11-16T02:00:00+00:00", 14)]
        c = surete.compteur(datetime(2026, 11, 15, 23, tzinfo=timezone.utc), couts, None, REGLAGES,
                            fin=datetime(2026, 11, 16, tzinfo=timezone.utc))
        self.assertAlmostEqual(c["dollars"], 3)


class Sanctions(unittest.TestCase):
    def test_seul_le_dernier_releve_compte(self):
        stats = [{"releve": "1", "chaine": "en", "video_id": "a", "titre": "A", "statut": "rejete:copyright"},
                 {"releve": "2", "chaine": "en", "video_id": "a", "titre": "A", "statut": "public"},
                 {"releve": "2", "chaine": "pt", "video_id": "b", "titre": "B", "statut": "rejete:termsOfUse"}]
        self.assertEqual(surete.sanctions(stats), [("pt", "b", "B", "rejete:termsOfUse")])


class Echecs(unittest.TestCase):
    def test_serie_en_cours_seulement(self):
        with tempfile.TemporaryDirectory() as d:
            lignes = [{"date": f"2026-11-11T0{i}:00", "quoi": "flux", "resultat": r}
                      for i, r in enumerate(["echec", "ok", "echec", "echec", "echec"])]
            lignes.append({"date": "2026-11-11T09:00", "quoi": "stats", "resultat": "echec"})
            Path(d, "chef-contenu.jsonl").write_text("\n".join(json.dumps(l) for l in lignes) + "\n", encoding="utf-8")
            self.assertEqual(surete.echecs_en_serie(Path(d), 3), [("flux", "2026-11-11T02:00", 3)])


class Questions(unittest.TestCase):
    def test_actions_fermees(self):
        for bonne in ("rien", "pause:flux", "reprise:chaine:en", "pause:tout", "reprise:pilote"):
            questions.verifier(bonne)
        for mauvaise in ("supprimer:flux", "pause:inconnu", "reprise:chaine:fr", "pause:", "rm -rf /", "reprise:flux;rien"):
            with self.assertRaises(ValueError):
                questions.verifier(mauvaise)

    def test_clic_attendu(self):
        self.assertTrue(questions.CLIC.match("q:1111-2140-1:oui"))
        for faux in ("q:1111:peut-etre", "q:../x:oui", "test:oui", "q:1111:oui;pause:tout"):
            self.assertIsNone(questions.CLIC.match(faux))

    def test_derniere_ligne_fait_foi(self):
        lignes = [{"id": "a", "etat": "ouverte"}, {"id": "a", "etat": "repondue"}, {"id": "b", "etat": "ouverte"}]
        etat = questions.etat_questions(lignes)
        self.assertEqual((etat["a"]["etat"], etat["b"]["etat"]), ("repondue", "ouverte"))

    def releve(self, envoi):
        """(réponses prises, clics marqués lus au Worker) pour un clic sur une question absente du registre."""
        clic = {"update_id": 42, "clic_id": "c1", "donnee": "q:1111-2140-1:oui", "message_id": 7, "envoi": envoi,
                "texte": "Je fusionne ?"}
        with mock.patch.object(questions.registre, "lire", return_value=[]), \
                mock.patch.object(questions, "telegram"), \
                mock.patch.object(questions, "alarme") as worker:
            worker.clics_recus.return_value = [clic]
            prises = questions.relever()
            lus = [i for appel in worker.clics_lus.call_args_list for i in appel.args[0]]
            return prises, lus

    def test_clic_recent_sur_question_inconnue_garde(self):
        self.assertEqual(self.releve(time.time() - 60), (0, []))

    def test_clic_ancien_sur_question_inconnue_oublie(self):
        self.assertEqual(self.releve(time.time() - 7 * 3600), (0, [42]))

    def test_message_dit_pourquoi_et_quand(self):
        texte = questions.message("Je reprends ?", "YouTube a refusé la vidéo X", "reprise:chaine:pt", "rien", "surete",
                                  "regarde d'abord", datetime(2026, 11, 11, 21, 30, tzinfo=timezone.utc))
        for attendu in ("Pourquoi : YouTube a refusé la vidéo X", "Pour t'aider à choisir : regarde d'abord",
                        "Oui : je relance les envois sur la chaîne A Cada Segundo (portugais)", "Non : ça reste en pause",
                        "vers 00h17"):
            self.assertIn(attendu, texte)

    def test_question_sans_pourquoi_refusee(self):
        with self.assertRaises(ValueError):
            questions.poser("Je reprends ?", "reprise:flux")


class BudgetLeveLundi(unittest.TestCase):
    def test_seule_la_pause_de_budget_d_une_semaine_passee_se_leve(self):
        pauses = [{"cible": "auteur", "action": "pause", "par": "surete", "raison": "budget semaine 2026-11-09 : 46 $"},
                  {"cible": "flux", "action": "pause", "par": "surete", "raison": "budget semaine 2026-11-09 : 46 $"},
                  {"cible": "direction", "action": "pause", "par": "jules", "raison": "budget semaine 2026-11-09"}]
        cibles = ["auteur", "flux", "direction"]
        self.assertEqual(surete.pauses_de_budget_perimees(cibles, pauses, "budget semaine 2026-11-16"), ["auteur", "flux"])
        self.assertEqual(surete.pauses_de_budget_perimees(cibles, pauses, "budget semaine 2026-11-09"), [])


class HorsPause(unittest.TestCase):
    def test_surete_et_reponses_echappent_a_la_pause_generale(self):
        scripts = organisation.scripts()
        self.assertTrue(scripts["reponses"].get("hors_pause"))
        self.assertTrue(scripts["garde_fous"].get("hors_pause"))
        self.assertFalse(scripts["flux"].get("hors_pause"))

    def test_pause_de_chaine(self):
        pauses = [{"cible": "chaine:en", "action": "pause", "par": "surete", "raison": "essai"}]
        self.assertIsNotNone(lancer.pause_active(["chaine:en"], pauses))
        self.assertIsNone(lancer.pause_active(["chaine:pt"], pauses))


if __name__ == "__main__":
    unittest.main()
