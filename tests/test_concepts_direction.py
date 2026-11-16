"""Demande #57 : les concepts du Veilleur dans le dossier de la Direction, et ses réponses.

python -m unittest discover tests
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import concepts, registre
from agents import direction


def fiche(i, **plus):
    return {"date": "2026-11-15T22:00:00+00:00", "par": "veilleur", "etat": "propose",
            "lien": f"https://www.youtube.com/shorts/{i:011d}", "titre": f"titre {i}", "chaine": "x", "vues": 5_000_000,
            "ratio": 900.0, "effort": "comme nos sujets", "destination": "nouvelle chaîne", "cout_estime_usd": 3.74, **plus}


class ConceptsDirection(unittest.TestCase):
    def setUp(self):
        self.dossier = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dossier, True)
        patch = mock.patch.object(registre, "DOSSIER", self.dossier)
        patch.start()
        self.addCleanup(patch.stop)
        (self.dossier / "concepts.jsonl").write_text(
            "".join(json.dumps(fiche(i)) + "\n" for i in range(3)), encoding="utf-8")
        self.ids = [c["id"] for c in concepts.ouverts()]

    def reponse(self, i, **plus):
        return {"id": self.ids[i], "reponse": "nouvelle_chaine", "raison": "5 M de vues", "potentiel": "viral",
                "limite": "", **plus}

    def test_le_dossier_liste_les_concepts_au_stade_propose(self):
        c = concepts.ouverts()
        self.assertEqual(len(c), 3)
        self.assertEqual(set(c[0]), {"id", "titre", "source", "vues", "ratio", "effort", "cout_estime_usd", "destination"})

    def test_une_reponse_fait_passer_le_stade_et_note_la_decision(self):
        faits, refus = concepts.appliquer([self.reponse(0), self.reponse(1, reponse="ecarte", potentiel="autre")])
        self.assertEqual((len(faits), refus), (2, []))
        self.assertEqual(len(concepts.ouverts()), 1)
        etats = sorted(c["etat"] for c in concepts.derniers().values())
        self.assertEqual(etats, ["ecarte", "nouvelle_chaine", "propose"])
        self.assertEqual(len(registre.decisions()), 2)

    def test_une_limite_laisse_le_stade_mais_note_la_decision(self):
        faits, _ = concepts.appliquer([self.reponse(0, limite="plus de budget Claude cette semaine")])
        self.assertEqual(len(concepts.ouverts()), 3)
        self.assertIn("faute de moyens", faits[0])
        self.assertEqual(len(registre.decisions()), 1)

    def test_une_reponse_hors_liste_est_refusee(self):
        faits, refus = concepts.appliquer([self.reponse(0, reponse="peut-etre"), self.reponse(1, potentiel="x"),
                                           self.reponse(2, raison=" "), {**self.reponse(0), "id": "inconnu"}])
        self.assertEqual((faits, len(refus)), ([], 4))
        self.assertEqual(len(concepts.ouverts()), 3)

    def test_un_concept_ne_recoit_qu_une_reponse_par_seance(self):
        faits, refus = concepts.appliquer([self.reponse(0), self.reponse(0, reponse="ecarte")])
        self.assertEqual((len(faits), len(refus)), (1, 1))

    def test_le_schema_ferme_les_reponses_aux_concepts_du_dossier(self):
        s = direction.schema(["chef-contenu"], concepts_ouverts=self.ids)
        self.assertIn("reponses_concepts", s["required"])
        item = s["properties"]["reponses_concepts"]["items"]
        self.assertEqual(item["properties"]["id"]["enum"], sorted(self.ids))
        self.assertEqual(item["properties"]["reponse"]["enum"], ["lancer_chaine_existante", "nouvelle_chaine", "ecarte"])
        self.assertEqual(item["properties"]["potentiel"]["enum"], ["viral", "affiliation", "autre"])
        self.assertEqual(s["properties"]["reponses_concepts"]["maxItems"], 3)
        self.assertEqual(direction.ids_concepts({"concepts": concepts.ouverts()}), self.ids)

    def test_appliquer_de_la_direction_passe_par_les_concepts(self):
        reponse = {"decisions": [], "retours": [], "consignes": [], "questions": [],
                   "reponses_concepts": [self.reponse(0)]}
        faits, refus = direction.appliquer(reponse, mock.MagicMock(), {})
        self.assertEqual(refus, [])
        self.assertTrue(any("concept" in f for f in faits))


if __name__ == "__main__":
    unittest.main()
