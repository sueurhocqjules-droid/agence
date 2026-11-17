"""La suite de tests ne modifie aucun fichier suivi par Git (demande #118).
Le nom en « zz » la fait passer en dernier. L'état est pris à l'import, avant tout test.  python -m unittest discover tests"""
import hashlib
import subprocess
import unittest
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def empreintes():
    try:
        sortie = subprocess.run(["git", "ls-files", "-z"], cwd=RACINE, capture_output=True, check=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    resultat = {}
    for nom in sortie.decode("utf-8").split("\0"):
        chemin = RACINE / nom
        if nom and chemin.is_file():
            resultat[nom] = hashlib.sha256(chemin.read_bytes()).hexdigest()
    return resultat


AVANT = empreintes()


class SuitePropre(unittest.TestCase):
    def test_aucun_fichier_suivi_n_a_change_pendant_la_suite(self):
        if AVANT is None:
            self.skipTest("Git indisponible")
        apres = empreintes()
        modifies = sorted(n for n in AVANT if apres.get(n) != AVANT[n])
        self.assertEqual(modifies, [], "des tests écrivent dans le dépôt : isoler dans un dossier temporaire")