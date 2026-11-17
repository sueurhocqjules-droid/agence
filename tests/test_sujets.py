"""Écriture des sujets par un modèle gratuit : format du JSON, secours, comptes du journal.  python -m unittest discover tests"""
import copy
import json
import sys
import unittest
from unittest import mock

from agence import organisation, postes, sujets

BON = {
    "sujet": {"en": {"titre": "What If You Folded Paper Once More Every Second?"},
              "es": {"titre": "¿Y si doblaras un papel una vez más cada segundo?"},
              "pt": {"titre": "E se você dobrasse um papel mais uma vez a cada segundo?"}},
    "calcul": {"regle": "Une pliure de plus chaque seconde", "resultat": "Après 42 pliures, l'épaisseur atteint la Lune",
               "etapes": [{"texte": "épaisseur d'une feuille", "valeur": 0.0001, "unite": "m"},
                          {"texte": "après 42 pliures", "valeur": 439804651.1, "unite": "m"},
                          {"texte": "distance Terre-Lune", "valeur": 384400000, "unite": "m"}],
               "descriptions": {"en": "Folding paper.", "es": "Doblar papel.", "pt": "Dobrar papel."}},
}


class Format(unittest.TestCase):
    def test_un_sujet_complet_passe(self):
        self.assertEqual(sujets.valider(BON), [])

    def test_ce_qui_manque_est_refuse(self):
        for chemin in [("sujet", "pt"), ("calcul", "etapes"), ("calcul", "descriptions", "es"), ("calcul", "resultat")]:
            d = copy.deepcopy(BON)
            cible = d
            for c in chemin[:-1]:
                cible = cible[c]
            del cible[chemin[-1]]
            self.assertTrue(sujets.valider(d), chemin)

    def test_etapes_et_valeurs_controlees(self):
        d = copy.deepcopy(BON)
        d["calcul"]["etapes"] = d["calcul"]["etapes"][:2]
        self.assertTrue(sujets.valider(d))
        d = copy.deepcopy(BON)
        d["calcul"]["etapes"][0]["valeur"] = "beaucoup"
        self.assertTrue(sujets.valider(d))
        d = copy.deepcopy(BON)
        d["sujet"]["en"]["titre"] = "x" * 101
        self.assertTrue(sujets.valider(d))

    def test_pas_un_objet(self):
        self.assertTrue(sujets.valider(None))
        self.assertTrue(sujets.valider([BON]))

    def test_le_format_decrit_au_modele_est_valide(self):
        self.assertIsInstance(json.loads(sujets.FORME), dict)
        self.assertIn(sujets.FORME, sujets.consigne("idée"))


class Modeles(unittest.TestCase):
    def test_ling_d_abord_puis_gpt_oss_et_jamais_claude(self):
        liste = postes.POSTES["ecrire-sujets"]
        self.assertEqual(liste[0][:2], ("openrouter", "inclusionai/ling-3.2-flash:free"))
        self.assertEqual(liste[1][:2], ("groq", "openai/gpt-oss-120b"))
        self.assertFalse([m for _, m, _ in liste if "claude" in m.lower()])

    def test_si_ling_ne_repond_pas_gpt_oss_ecrit(self):
        def appeler(fournisseur, modele, consigne, plafond, **_):
            if fournisseur == "openrouter":
                raise RuntimeError("HTTP 429")
            return "```json\n" + json.dumps(BON) + "\n```", 1, 1, 0.1
        with mock.patch.object(postes, "appeler", appeler), \
                mock.patch.object(postes, "PANNES", postes.PANNES.with_name("absent.json")):
            donnees, modele = sujets.ecrire("papier")
        self.assertEqual(modele, "openai/gpt-oss-120b")
        self.assertEqual(donnees, BON)

    def test_une_reponse_hors_format_leve_valeur(self):
        with mock.patch.object(postes, "demander", return_value=('{"sujet": 1}', "m", 1, 1, 0.1)):
            with self.assertRaises(ValueError):
                sujets.ecrire("papier")


class Journal(unittest.TestCase):
    def test_le_journal_compte_ecrits_et_acceptes(self):
        info = {"appels_gratuits": 0}

        class Seance:
            def __enter__(self):
                return info

            def __exit__(self, *a):
                return False

        reponses = [(BON, "m"), ValueError("hors format"), RuntimeError("aucun modèle")]
        with mock.patch.object(sujets, "ecrire", side_effect=reponses), \
                mock.patch.object(sujets.registre, "seance", return_value=Seance()), \
                mock.patch.object(sys, "argv", ["sujets", "a", "b", "c"]), mock.patch("builtins.print"):
            sujets.main()
        self.assertEqual(info["resultat"], "ok : 2 sujets écrits, 1 acceptés")


class Fiche(unittest.TestCase):
    def test_le_script_a_son_proprietaire_et_ses_cles(self):
        s = organisation.scripts()["sujets"]
        self.assertEqual(s["proprietaire"], "programmateur")
        self.assertIn("sujets", organisation.fiches()["programmateur"]["scripts"])
        self.assertEqual(organisation.cles_accordees("sujets", s["secrets"]), ({"OPENROUTER_API_KEY", "GROQ_API_KEY"}, []))


if __name__ == "__main__":
    unittest.main()
