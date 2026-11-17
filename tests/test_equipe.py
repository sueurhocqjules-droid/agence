"""L'équipe du Pilote : seuls des modules de equipe/, seules les clés gratuites, un temps borné.
python -m unittest discover tests"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import equipe


class Membres(unittest.TestCase):
    def test_seuls_les_modules_de_equipe_avec_un_nom_simple(self):
        liste, erreurs = equipe.membres("""
[[membre]]
nom = "veille"
module = "equipe.veille"
minutes = 50
[[membre]]
nom = "flux"
module = "agents.flux"
[[membre]]
nom = "../x"
module = "equipe.x"
[[membre]]
nom = "ok2"
module = "equipe.ok2"
args = ["--a", 3]
""")
        self.assertEqual([(m["nom"], m["minutes"]) for m in liste], [("veille", equipe.MINUTES_MAX)])
        self.assertEqual(len(erreurs), 3)

    def test_fichier_illisible_ne_lance_rien(self):
        liste, erreurs = equipe.membres("[[membre]\n")
        self.assertEqual(liste, [])
        self.assertTrue(erreurs)


class Environnement(unittest.TestCase):
    def test_seules_les_cles_gratuites_passent(self):
        env = equipe.env_membre({"GROQ_API_KEY": "g", "YOUTUBE_API_KEY": "y", "GH_TOKEN": "x", "META_TOKEN": "m",
                                 "YT_TOKEN_EN": "t", "CLAUDE_CODE_OAUTH_TOKEN": "c", "PATH": "/bin"})
        self.assertEqual(set(env), {"GROQ_API_KEY", "YOUTUBE_API_KEY", "PATH", "PYTHONUTF8"})


class Lancement(unittest.TestCase):
    def test_un_membre_trop_long_est_coupe_et_le_suivant_tourne(self):
        def executer(commande, **k):
            if commande[-1] == "equipe.lent":
                raise subprocess.TimeoutExpired(commande, k["timeout"])
            return subprocess.CompletedProcess(commande, 0, "fini", "")

        liste = [{"nom": "lent", "module": "equipe.lent", "minutes": 1, "args": []},
                 {"nom": "vite", "module": "equipe.vite", "minutes": 1, "args": []}]
        with tempfile.TemporaryDirectory() as d, mock.patch.object(equipe.registre, "DOSSIER", Path(d)):
            r = equipe.faire_tourner(liste, executer=executer, environ={"PATH": "/bin"})
        self.assertEqual([x["resultat"] for x in r], ["coupé après 1 min", "ok"])


if __name__ == "__main__":
    unittest.main()
