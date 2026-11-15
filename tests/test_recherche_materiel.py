"""Recherche : un outil dit ce qu'il remplace et le matériel qu'il demande ; sans le matériel de l'agence, il sort.
python -m unittest discover tests"""
import unittest

from agents import chef_recherche
from agents.chercheur_outils import valider

LIEN = "https://github.com/a/b"
BON = {"nom": "Outil", "lien": LIEN, "remplace": "auteur", "gratuit": True, "pourquoi": "écrit le texte", "essai": "un test",
       "part_remplacee": "le texte seulement", "materiel_requis": "aucun", "tourne_chez_nous": True}


class MaterielRequis(unittest.TestCase):
    def test_chercheur_ecarte_un_outil_qui_demande_un_gpu(self):
        gardes, ecartes = valider({"candidats": [{**BON, "tourne_chez_nous": False, "materiel_requis": "GPU 24 Go"}]},
                                  {LIEN}, {"auteur"}, set())
        self.assertEqual(gardes, [])
        self.assertIn("matériel", ecartes[0]["raison"])

    def test_chercheur_garde_les_champs(self):
        gardes, _ = valider({"candidats": [BON]}, {LIEN}, {"auteur"}, set())
        self.assertEqual((gardes[0]["part_remplacee"], gardes[0]["tourne_chez_nous"]), ("le texte seulement", True))

    def test_chef_ne_voit_pas_un_outil_sans_le_materiel(self):
        outils = [{"lien": "a", "etat": "propose", "tourne_chez_nous": False}, {"lien": "b", "etat": "propose"},
                  {"lien": "c", "etat": "propose", "tourne_chez_nous": True}]
        self.assertEqual(sorted(chef_recherche.indexer([], outils)), ["b", "c"])

    def test_chef_recopie_la_partie_remplacee(self):
        fiche = {"lien": "c", "etat": "propose", "nom": "X", "part_remplacee": "texte", "materiel_requis": "aucun",
                 "tourne_chez_nous": True}
        par_lien = chef_recherche.indexer([], [fiche])
        reponse = {"propositions": [{"source": "c", "titre": "t", "proposition": "p", "preuve": "x",
                                     "mesure": "cout_claude_semaine", "attendu": 20, "echeance_jours": 14}]}
        gardes, _ = chef_recherche.valider(reponse, par_lien, {"cout_claude_semaine": 30})
        self.assertEqual(gardes[0]["preuves_chiffrees"]["part_remplacee"], "texte")
        self.assertEqual(gardes[0]["preuves_chiffrees"]["materiel_requis"], "aucun")


if __name__ == "__main__":
    unittest.main()
