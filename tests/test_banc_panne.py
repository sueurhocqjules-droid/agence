"""Un banc des agents rouge laisse sa cause au journal, avec le lien du run (demande #96).

python -m unittest discover tests
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import banc_agents, registre

LIGNES = ["VERT a : passe, attendu passe", "        c1 : passe",
          "ROUGE b : echec, attendu passe", "        c2 : echec (motifs interdits trouvés : ['x'])"]
ENV = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "o/d", "GITHUB_RUN_ID": "42"}


class PanneDuBanc(unittest.TestCase):
    def ecrire(self, env):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(registre, "DOSSIER", Path(tmp)), \
                mock.patch.dict(os.environ, env, clear=True):
            banc_agents.noter_panne(LIGNES, "Banc des agents : 2 cas joués, 1 rouge(s)")
            lu = (Path(tmp) / "journal" / "chef-operations.jsonl").read_text(encoding="utf-8")
        return json.loads(lu)

    def test_la_cause_et_le_lien_du_run_sont_au_journal(self):
        entree = self.ecrire(ENV)
        self.assertIn("https://github.com/o/d/actions/runs/42", entree["bloquant"])
        self.assertIn("ROUGE b", entree["sortie"])
        self.assertIn("c2 : echec", entree["sortie"])
        self.assertNotIn("VERT a", entree["sortie"])

    def test_hors_github_pas_de_lien(self):
        self.assertNotIn("http", self.ecrire({})["bloquant"])


if __name__ == "__main__":
    unittest.main()
