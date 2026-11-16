"""Journal de l'Auteur : les séances de l'atelier sont notées au format du lanceur, une seule fois."""
import json
import tempfile
import unittest
from pathlib import Path

from agents import surete


def seance(debut, dollars, sujets, fin=""):
    return {"debut": debut, "fin": fin, "agent": "auteur", "dollars_equiv": dollars, "sujets": sujets}


class JournalAuteur(unittest.TestCase):
    def lignes(self, d):
        return [json.loads(l) for l in (Path(d) / "auteur.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_une_ligne_par_seance_au_format_du_lanceur(self):
        with tempfile.TemporaryDirectory() as d:
            n = surete.journaliser_atelier([seance("2026-11-16T01:00:00+00:00", "8.1", "2", "2026-11-16T02:10:00+00:00"),
                                            seance("2026-11-09T01:00:00+00:00", "3", "0")], Path(d))
            a, b = self.lignes(d)
        self.assertEqual(n, 2)
        self.assertEqual((a["quoi"], a["resultat"], a["etat"], a["dollars_equiv"], a["sujets"]), ("atelier", "ok", "livre", 8.1, 2))
        self.assertEqual((a["debut"], a["fin"]), ("2026-11-16T01:00:00+00:00", "2026-11-16T02:10:00+00:00"))
        self.assertEqual((b["resultat"], b["etat"], b["fin"]), ("vide", "rien livre", b["debut"]))

    def test_une_seance_deja_notee_ne_l_est_pas_deux_fois(self):
        with tempfile.TemporaryDirectory() as d:
            s = seance("2026-11-16T01:00:00+00:00", "8.1", "2")
            surete.journaliser_atelier([s], Path(d))
            self.assertEqual(surete.journaliser_atelier([s, seance("2026-11-23T01:00:00+00:00", "1", "1")], Path(d)), 1)
            self.assertEqual(len(self.lignes(d)), 2)

    def test_atelier_illisible_n_ecrit_rien(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(surete.journaliser_atelier(None, Path(d)), 0)
            self.assertFalse((Path(d) / "auteur.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
