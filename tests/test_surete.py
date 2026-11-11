"""Tests de l'étape 6 : compteur, seuils, sanctions, pannes, questions à choix fermés, bilan.  python -m unittest discover tests"""
import json
import tempfile
import time
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

from agence import lancer, organisation, questions
from agents import bilan, surete

REGLAGES = {"claude": {"dollars_par_pourcent": 0, "limite_pourcent": 20}}
MERCREDI = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)
LUNDI_MATIN = datetime(2026, 11, 16, 7, tzinfo=timezone.utc)


def cout(agent, quand, dollars=0, appels=0):
    return {"agent": agent, "debut": quand, "dollars_equiv": str(dollars), "appels_gratuits": str(appels)}


class Compteur(unittest.TestCase):
    def test_semaine_en_cours_seulement(self):
        couts = [cout("auteur", "2026-11-08T23:00:00+00:00", 50), cout("auteur", "2026-11-10T02:00:00+00:00", 14.2),
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
        couts = [cout("auteur", "2026-11-12T00:00:00+00:00", 3), cout("auteur", "2026-11-16T02:00:00+00:00", 14)]
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
        for bonne in ("rien", "pause:flux", "reprise:chaine:en", "pause:tout", "reprise:auteur"):
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
        with tempfile.TemporaryDirectory() as d,                 mock.patch.object(questions, "DECALAGE", Path(d, "telegram.json")),                 mock.patch.object(questions.registre, "lire", return_value=[]),                 mock.patch.object(questions, "telegram") as tg:
            tg.clics.return_value = (43, [(42, "c1", "q:1111-2140-1:oui", 7, envoi)])
            prises = questions.relever()
            return prises, json.loads(questions.DECALAGE.read_text())["decalage"]

    def test_clic_recent_sur_question_inconnue_garde(self):
        self.assertEqual(self.releve(time.time() - 60), (0, 42))

    def test_clic_ancien_sur_question_inconnue_oublie(self):
        self.assertEqual(self.releve(time.time() - 7 * 3600), (0, 43))


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


class Bilan(unittest.TestCase):
    def test_un_lundi_couvre_la_semaine_passee(self):
        debut, fin = bilan.periode(LUNDI_MATIN)
        self.assertEqual((debut.day, fin.day, fin.hour), (9, 16, 0))

    def test_vues_gagnees_et_sorties(self):
        stats = [{"releve": "2026-11-08T12:00:00+00:00", "chaine": "en", "video_id": "a", "titre": "A", "statut": "public",
                  "sortie": "2026-11-01T00:00:00+00:00", "vues": "100"},
                 {"releve": "2026-11-15T12:00:00+00:00", "chaine": "en", "video_id": "a", "titre": "A", "statut": "public",
                  "sortie": "2026-11-01T00:00:00+00:00", "vues": "150"},
                 {"releve": "2026-11-15T12:00:00+00:00", "chaine": "en", "video_id": "b", "titre": "B", "statut": "public",
                  "sortie": "2026-11-12T00:00:00+00:00", "vues": "80"},
                 {"releve": "2026-11-16T12:00:00+00:00", "chaine": "en", "video_id": "b", "titre": "B", "statut": "public",
                  "sortie": "2026-11-12T00:00:00+00:00", "vues": "999"}]
        debut, fin = bilan.periode(LUNDI_MATIN)
        par_chaine, _, avant = bilan.chaines(stats, debut, fin)
        self.assertEqual(par_chaine["en"]["gagnees"], 130)
        self.assertEqual(par_chaine["en"]["sorties"], 1)
        self.assertEqual(par_chaine["en"]["meilleure"][0], "B")
        self.assertIsNotNone(avant)


if __name__ == "__main__":
    unittest.main()
