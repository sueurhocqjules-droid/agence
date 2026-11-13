"""Alarme hors de GitHub (sous-étape 17) : le signe de vie du réveil et les décisions du Worker.

python -m unittest discover tests
"""
import io
import json
import os
import shutil
import subprocess
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from agence import alarme

RACINE = Path(__file__).resolve().parent.parent
HEURE = 3_600_000


class Reponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class Signe(unittest.TestCase):
    def test_sans_secret_rien_ne_part(self):
        appels = []
        with mock.patch.dict(os.environ, {"ALARME_SECRET": ""}):
            self.assertFalse(alarme.signe(ouvrir=lambda *a, **k: appels.append(a)))
        self.assertEqual(appels, [])

    def test_le_secret_part_dans_l_en_tete_jamais_dans_l_adresse(self):
        vues = []

        def ouvrir(requete, timeout):
            vues.append(requete)
            return Reponse(b'{"ok": true, "dernier": "2026-11-14T00:00:00Z"}')

        with mock.patch.dict(os.environ, {"ALARME_SECRET": "s3cret"}):
            self.assertTrue(alarme.signe(ouvrir=ouvrir))
        requete = vues[0]
        self.assertEqual(requete.get_method(), "POST")
        self.assertEqual(requete.get_header("Authorization"), "Bearer s3cret")
        self.assertNotIn("s3cret", requete.full_url)
        self.assertEqual(requete.full_url, alarme.ADRESSE)

    def test_un_refus_ou_une_panne_ne_casse_jamais_le_reveil(self):
        def refus(requete, timeout):
            raise urllib.error.HTTPError(requete.full_url, 401, "non", {}, None)

        def panne(requete, timeout):
            raise urllib.error.URLError("injoignable")

        with mock.patch.dict(os.environ, {"ALARME_SECRET": "s3cret"}):
            self.assertFalse(alarme.signe(ouvrir=refus))
            self.assertFalse(alarme.signe(ouvrir=panne))

    def test_le_reveil_envoie_le_signe_meme_si_un_agent_a_echoue(self):
        texte = (RACINE / ".github/workflows/reveil.yml").read_text(encoding="utf-8")
        etape = texte.split("- name: Signe de vie")[1]
        self.assertIn("if: always()", etape)
        self.assertIn("python -m agence.alarme signe", etape)
        self.assertIn("ALARME_SECRET: ${{ secrets.ALARME_SECRET }}", etape)


class Deploiement(unittest.TestCase):
    def test_liaisons_du_worker(self):
        meta = alarme.metadonnees("kv", alarme.DELAI_MINUTES, False, "s", "b", "c")
        liaisons = {l["name"]: l for l in meta["bindings"]}
        self.assertEqual(liaisons["DELAI_MINUTES"]["text"], "1440")
        self.assertEqual(liaisons["ESSAI"]["text"], "")
        for nom in ("SIGNE_SECRET", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
            self.assertEqual(liaisons[nom]["type"], "secret_text")   # jamais en clair dans le tableau de bord
        self.assertEqual(liaisons["ETAT"]["type"], "kv_namespace")
        self.assertEqual(alarme.metadonnees("kv", 2, True, "s", "b", "c")["bindings"][2]["text"], "1")

    def test_le_delai_normal_couvre_les_retards_connus_de_github(self):
        self.assertGreaterEqual(alarme.DELAI_MINUTES, 19 * 60)   # un créneau sauté et un autre retardé de 7 h (11/11)
        self.assertEqual(alarme.CRON, "7 * * * *")

    def test_le_secret_partage_n_est_jamais_suivi_par_git(self):
        self.assertIn(".secrets/", (RACINE / ".gitignore").read_text(encoding="utf-8").splitlines())


@unittest.skipUnless(shutil.which("node"), "Node absent")
class Worker(unittest.TestCase):
    """Les fonctions pures de alarme/worker.js, exécutées par Node."""

    def js(self, expression):
        source = (RACINE / "alarme/worker.js").as_uri()
        code = f"import * as w from '{source}'; console.log(JSON.stringify({expression}));"
        sortie = subprocess.run(["node", "--input-type=module", "-e", code], capture_output=True, text=True, check=True)
        return json.loads(sortie.stdout)

    def test_silence_court_rien(self):
        self.assertIsNone(self.js(f"w.decider(Date.parse('2026-11-14T10:00:00Z'), "
                                  f"{{dernier: '2026-11-14T00:00:00Z'}}, 1440)"))

    def test_silence_long_alarme(self):
        self.assertEqual(self.js(f"w.decider(Date.parse('2026-11-15T01:00:00Z'), "
                                 f"{{dernier: '2026-11-14T00:00:00Z'}}, 1440)"), {"minutes": 25 * 60})

    def test_un_rappel_par_delai_pas_plus(self):
        etat = "{dernier: '2026-11-14T00:00:00Z', alerte: '2026-11-15T00:07:00Z'}"
        self.assertIsNone(self.js(f"w.decider(Date.parse('2026-11-15T05:07:00Z'), {etat}, 1440)"))
        self.assertIsNotNone(self.js(f"w.decider(Date.parse('2026-11-16T00:07:00Z'), {etat}, 1440)"))

    def test_jamais_de_signe_rien(self):
        self.assertIsNone(self.js("w.decider(Date.now(), {}, 1440)"))

    def test_le_retour_n_est_annonce_qu_apres_une_vraie_alarme(self):
        vraie = self.js("w.apresSigne(0, {dernier: 'x', alerte: '2026-11-14T00:00:00Z', alerte_essai: false}, 'réveil')")
        essai = self.js("w.apresSigne(0, {dernier: 'x', alerte: '2026-11-14T00:00:00Z', alerte_essai: true}, 'réveil')")
        calme = self.js("w.apresSigne(0, {dernier: 'x', alerte: null}, 'réveil')")
        self.assertEqual([vraie["retour"], essai["retour"], calme["retour"]], [True, False, False])
        self.assertIsNone(vraie["etat"]["alerte"])

    def test_messages(self):
        essai = self.js("w.messageAlarme({dernier: '2026-11-14T00:00:00Z', source: 'réveil'}, 1500, true)")
        self.assertTrue(essai.startswith("[TEST"))
        self.assertIn("25 h", essai)
        service = self.js("w.messageAlarme({dernier: '2026-11-14T00:00:00Z', source: 'mise en service'}, 1500, false)")
        self.assertIn("ALARME_SECRET", service)
        self.assertNotIn("TEST", service)


if __name__ == "__main__":
    unittest.main()
