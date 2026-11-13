"""Tests de la portée des chaînes : panne face aux chaînes sœurs, chute d'une semaine à l'autre, alerte et bilan.
python -m unittest discover tests"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from agence import mesures
from agents import surete

A = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)  # dimanche soir, séance de la Direction


def releve(a, vues_par_chaine, debut):
    """Un relevé à la date `a` : pour chaque chaîne, une vidéo publique par jour à partir de `debut`."""
    lignes = []
    for chaine, vues in vues_par_chaine.items():
        for i, v in enumerate(vues):
            sortie = (debut + timedelta(days=i)).strftime("%Y-%m-%dT15:00:00Z")
            lignes.append({"releve": a.isoformat(timespec="seconds"), "chaine": chaine, "video_id": f"{chaine}{debut:%d}{i}",
                           "titre": "t", "statut": "public", "sortie": sortie, "vues": str(v), "likes": "0",
                           "commentaires": "0"})
    return lignes


def semaine(a, vues_par_chaine):
    """Les vidéos sorties dans la fenêtre de la semaine qui précède `a` (7 jours finissant 2 jours avant)."""
    return releve(a - timedelta(hours=1), vues_par_chaine, a - mesures.RECUL - mesures.SEMAINE + timedelta(hours=1))


class Portee(unittest.TestCase):
    def test_chaine_non_diffusee_face_a_ses_soeurs(self):
        stats = semaine(A, {"en": [1000] * 7, "es": [0, 1, 0, 2, 0, 0, 0], "pt": [40] * 7})
        p = mesures.portee(stats, A)
        self.assertTrue(p["es"]["panne"])
        self.assertFalse(p["pt"]["panne"])  # 4 % de en : moins diffusée, mais diffusée
        self.assertFalse(p["en"]["panne"])
        signaux = mesures.signaux_portee(stats, A)
        self.assertEqual([(s["chaine"], s["signal"], s["semaines"]) for s in signaux], [("es", "panne", 1)])
        self.assertIn("moins de 0,1 %", signaux[0]["texte"])

    def test_tout_le_monde_bas_rien_a_comparer(self):
        stats = semaine(A, {"en": [20] * 7, "es": [0] * 7, "pt": [5] * 7})
        self.assertEqual(mesures.signaux_portee(stats, A), [])

    def test_trop_peu_de_videos(self):
        stats = semaine(A, {"en": [1000] * 7, "es": [0, 0], "pt": [500] * 7})
        self.assertFalse(mesures.portee(stats, A)["es"]["panne"])

    def test_chute_mais_pas_pour_une_virale_isolee(self):
        debut_avant = A - mesures.RECUL - 2 * mesures.SEMAINE + timedelta(hours=1)
        debut = debut_avant + mesures.SEMAINE
        avant = {"en": [1000] * 7, "es": [300] * 7, "pt": [40, 30, 1224, 35, 50, 30, 45]}
        cette = {"en": [1000] * 7, "es": [20] * 7, "pt": [35, 30, 40, 33, 13, 16, 30]}
        stats = releve(A - timedelta(hours=1), avant, debut_avant) + releve(A - timedelta(hours=1), cette, debut)
        p = mesures.portee(stats, A)
        self.assertTrue(p["es"]["chute"])     # médiane 300 puis 20
        self.assertFalse(p["pt"]["chute"])    # la virale à 1 224 ne compte pas : médiane 40 puis 33
        self.assertFalse(p["en"]["chute"])

    def test_semaines_d_affilee(self):
        stats = []
        for k in range(3):  # trois semaines de panne, chacune avec son relevé
            stats += semaine(A - k * mesures.SEMAINE, {"en": [900] * 7, "es": [0] * 7, "pt": [60] * 7})
        self.assertEqual(mesures.semaines_de_suite(stats, A, "es", "panne"), 3)
        self.assertEqual(mesures.semaines_de_suite(stats, A, "pt", "panne"), 0)


class AlerteSurete(unittest.TestCase):
    def alertes(self, semaines_de_panne, deja=()):
        stats = []
        for k in range(semaines_de_panne):
            stats += semaine(A - k * mesures.SEMAINE, {"en": [900] * 7, "es": [0] * 7, "pt": [60] * 7})
        with mock.patch.object(surete.registre, "lire", return_value=[]):
            s = surete.Surete(essai=True)
        s.deja = set(deja)
        envoyees = []
        alerter = s.alerter
        def espion(cle, niveau, message):
            parti = alerter(cle, niveau, message)
            envoyees.append((cle, niveau, message, parti))
            return parti
        s.alerter = espion
        surete.alerter_portee(s, stats, A)
        return envoyees, s

    def test_premiere_semaine_la_direction_s_en_occupe(self):
        envoyees, _ = self.alertes(1)
        self.assertEqual(len(envoyees), 1)
        cle, niveau, message, parti = envoyees[0]
        self.assertTrue(parti)
        self.assertEqual(cle, f"portee:es:panne:{surete.lancer.debut_semaine(A):%Y-%m-%d}")
        self.assertEqual(niveau, "diffusion")
        self.assertIn("Rien à faire pour l'instant", message)

    def test_ca_continue_solutions_a_jules(self):
        envoyees, _ = self.alertes(2)
        self.assertIn("te propose ses solutions dans le mail de lundi", envoyees[0][2])

    def test_deja_envoyee_cette_semaine(self):
        cle = f"portee:es:panne:{surete.lancer.debut_semaine(A):%Y-%m-%d}"
        envoyees, _ = self.alertes(1, deja=[cle])
        self.assertEqual([e[3] for e in envoyees], [False])


if __name__ == "__main__":
    unittest.main()
