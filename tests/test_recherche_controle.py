"""Recherche : le script rejette une proposition qui ne reprend pas ses preuves, ou tirée d'une publicité de marque.
python -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path

from agence import registre
from agents import chef_recherche

VIDEO = "https://www.youtube.com/shorts/abc"
OUTIL = "https://github.com/a/outil"
CONCEPT = {"lien": VIDEO, "etat": "propose", "titre": "How a Bridge Is Built", "chaine": "Bridge Lab", "vues": 1200000,
           "concept": "pont", "pourquoi_ca_marche": "pas à pas"}
FICHE_OUTIL = {"lien": OUTIL, "etat": "propose", "nom": "Outil", "economie_usd_semaine": 10.2}
PAR_LIEN = {VIDEO: ("concept", CONCEPT), OUTIL: ("outil", FICHE_OUTIL)}


def concept(**changes):
    g = {"type": "concept", "source": VIDEO, "titre": "How a Bridge Is Built en 3 langues", "proposition": "Produire",
         "preuve": "1 200 000 vues", "preuves_chiffrees": {"titre": CONCEPT["titre"], "chaine": "Bridge Lab", "vues": 1200000}}
    return {**g, **changes}


def outil(**changes):
    g = {"type": "outil", "source": OUTIL, "titre": "Adopter Outil", "proposition": "Intégrer", "preuve": "10,2 $ économisés par semaine",
         "preuves_chiffrees": {"nom": "Outil", "economie_usd_semaine": 10.2}}
    return {**g, **changes}


def raison(g, par_lien=PAR_LIEN):
    gardes, refus = chef_recherche.controler([g], par_lien)
    return None if gardes else refus[0]["raison"]


class Controle(unittest.TestCase):
    def test_propositions_saines_gardees(self):
        self.assertIsNone(raison(concept()))
        self.assertIsNone(raison(outil()))

    def test_titre_hors_preuves(self):
        self.assertIn("titre", raison(concept(titre="Un sous-marin en 3 langues")))
        self.assertIn("titre", raison(outil(titre="Adopter Inkling")))

    def test_source_qui_n_est_pas_le_lien_cite(self):
        autre = {**PAR_LIEN, VIDEO: ("concept", {**CONCEPT, "lien": "https://www.youtube.com/shorts/autre"})}
        self.assertIn("source", raison(concept(), autre))

    def test_economie_differente(self):
        self.assertIn("économie", raison(outil(preuve="100,98 $ économisés par semaine")))
        self.assertIn("économie", raison(outil(proposition="Une économie de 25 $ par semaine")))

    def test_vues_differentes(self):
        self.assertIn("vues", raison(concept(preuve="34 979 622 vues")))

    def test_vues_prevues_ne_comptent_pas(self):
        self.assertIsNone(raison(concept(preuve="1 200 000 vues, on prévoit 30 000 vues supplémentaires")))

    def test_publicite_de_marque(self):
        marque = {**CONCEPT, "chaine": "Philips Healthcare"}
        self.assertIn("publicité", raison(concept(), {VIDEO: ("concept", marque)}))
        pub = {**CONCEPT, "concept": "Publicité de marque sur un pont"}
        self.assertIn("publicité", raison(concept(), {VIDEO: ("concept", pub)}))

    def test_refus_ecrits_avec_la_raison(self):
        with tempfile.TemporaryDirectory() as tmp:
            ancien, registre.DOSSIER = registre.DOSSIER, Path(tmp)
            try:
                chef_recherche.ecrire_refus([{"source": VIDEO, "raison": "titre"}])
                ligne = json.loads((Path(tmp) / "refus.jsonl").read_text(encoding="utf-8"))
                self.assertEqual(registre.refuses(), {VIDEO})
            finally:
                registre.DOSSIER = ancien
        self.assertEqual((ligne["par"], ligne["lien"]), ("chef-recherche", VIDEO))
        self.assertIn("titre", ligne["raison"])


if __name__ == "__main__":
    unittest.main()
