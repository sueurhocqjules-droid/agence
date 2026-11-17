"""Tests du journal de l'Auteur (agence/auteur.py).  python -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import auteur, registre

CSV = ("date,cout_usd_equivalent,sujets,reserve_usd\n"
       "2026-11-12T01:00:00+00:00,3.74,2,0\n"
       "2026-11-12T14:00:00+00:00,8.0,0,0\n"
       "2026-11-13T01:00:00+00:00,2.5,,0\n")


class JournalAuteur(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.couts = self.tmp / "couts.csv"
        self.couts.write_text(CSV, encoding="utf-8")
        mock.patch.object(registre, "DOSSIER", self.tmp).start()
        self.addCleanup(mock.patch.stopall)

    def lignes(self):
        f = self.tmp / "journal" / "auteur.jsonl"
        return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines()]

    def test_une_ligne_par_seance(self):
        auteur.noter_seances(self.couts)
        l = self.lignes()
        self.assertEqual([x["sujets"] for x in l], [2, 0, None])
        self.assertEqual(l[0]["cout_usd"], 3.74)
        self.assertEqual([x["echec"] for x in l], [False, True, None])

    def test_pas_de_fausse_panne_pour_la_surete(self):
        auteur.noter_seances(self.couts)
        self.assertNotIn("echec", {x["resultat"] for x in self.lignes()})

    def test_une_seance_n_est_notee_qu_une_fois(self):
        auteur.noter_seances(self.couts)
        self.assertEqual(auteur.noter_seances(self.couts), [])
        with open(self.couts, "a", encoding="utf-8") as f:
            f.write("2026-11-14T01:00:00+00:00,4,3,0\n")
        self.assertEqual(len(auteur.noter_seances(self.couts)), 1)
        self.assertEqual(len(self.lignes()), 4)

    def test_fichier_absent(self):
        self.assertEqual(auteur.noter_seances(self.tmp / "absent.csv"), [])


if __name__ == "__main__":
    unittest.main()
