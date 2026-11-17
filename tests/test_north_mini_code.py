"""Essai de cohere/north-mini-code:free (demande #52) : sans réseau, appels simulés.

Ce que le test prouve : l'outil passe par OpenRouter, qui exige une clé de compte même pour un modèle à 0 $.
L'essai demandé est sans compte ni clé : il ne passe donc pas, et le catalogue ne change pas.
"""
import io
import json
import unittest
from pathlib import Path
from unittest import mock

from agence import catalogue, modeles

MODELE = "cohere/north-mini-code:free"
LIEN = "https://openrouter.ai/cohere/north-mini-code:free"
REPONSE = {"choices": [{"message": {"content": "export const Scene = () => null;"}}],
           "usage": {"prompt_tokens": 20, "completion_tokens": 10}}
SANS_FICHIER = Path("/inexistant/.env")


class EssaiNorthMiniCode(unittest.TestCase):
    def test_l_outil_demande_une_cle_de_compte(self):
        vues = []

        def ouvrir(requete, timeout=None):
            vues.append(requete)
            return io.StringIO(json.dumps(REPONSE))

        with mock.patch.dict("os.environ", {"OPENROUTER_API_KEY": "cle-factice"}, clear=True), \
                mock.patch.object(modeles, "ENV_LOCAL", SANS_FICHIER), \
                mock.patch("urllib.request.urlopen", ouvrir):
            texte = modeles.appeler("openrouter", MODELE, "Écris la composition Remotion du sujet.")[0]
        self.assertIn("Scene", texte)
        self.assertEqual(json.loads(vues[0].data)["model"], MODELE)
        self.assertEqual(vues[0].get_header("Authorization"), "Bearer cle-factice")

    def test_sans_cle_aucun_acces(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(modeles, "ENV_LOCAL", SANS_FICHIER):
            self.assertIsNone(modeles.cle("openrouter"))

    def test_voie_du_catalogue_avec_compte(self):
        self.assertEqual(catalogue.voie({"gratuit": True, "compte_requis": True}), catalogue.GUICHET)

    def test_catalogue_inchange(self):
        self.assertNotIn(LIEN, catalogue.inscrits())


if __name__ == "__main__":
    unittest.main()
