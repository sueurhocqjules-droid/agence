"""Le Pilote : ce que son script garde, son budget, son rapport et son environnement.  python -m unittest discover tests"""
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from agence import pilote

MERCREDI = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
REGLAGES = {"claude": {"pause_usd_semaine": 70, "dollars_par_pourcent": 0}}


def cout(dollars, debut="2026-11-17T02:00:00+00:00"):
    return {"debut": debut, "agent": "pilote", "dollars_equiv": str(dollars), "appels_gratuits": "0"}


class Proteges(unittest.TestCase):
    def test_ce_qui_fixe_ses_limites_ou_le_controle_est_protege(self):
        for chemin in (".github/workflows/reveil.yml", "organisation/MISSION.md", "organisation/seuils.toml",
                       "organisation/autorisations.toml", "organisation/scripts.toml", "agence/pilote.py",
                       "agence/lancer.py", "agence/relecture.py", "agents/surete.py", "tests/test_pilote.py",
                       "registre/couts.csv", "registre/revenu.jsonl", "registre/pauses.csv"):
            self.assertTrue(pilote.protege(chemin), chemin)

    def test_son_carnet_et_ses_outils_sont_a_lui(self):
        for chemin in ("registre/pilote/carnet.md", "registre/pilote/rapport.json", "agents/flux.py",
                       "organisation/rythme.toml", "organisation/PILOTE.md", "organisation/diffusion.toml",
                       "tests/test_flux.py", "agence/gabarits.py"):
            self.assertFalse(pilote.protege(chemin), chemin)


class Budget(unittest.TestCase):
    def test_le_plafond_est_le_plus_petit_du_reste_et_de_son_choix(self):
        plafond, depense, pause = pilote.plafond_seance(MERCREDI, [cout(43)], None, REGLAGES, {"usd_max_seance": 15})
        self.assertEqual((plafond, depense, pause), (15, 43, 70))
        plafond, _, _ = pilote.plafond_seance(MERCREDI, [cout(63)], None, REGLAGES, {"usd_max_seance": 15})
        self.assertAlmostEqual(plafond, 7)

    def test_sans_choix_tout_le_reste_et_jamais_negatif(self):
        self.assertAlmostEqual(pilote.plafond_seance(MERCREDI, [cout(20)], None, REGLAGES, {})[0], 50)
        self.assertEqual(pilote.plafond_seance(MERCREDI, [cout(90)], None, REGLAGES, {"usd_max_seance": 15})[0], 0)

    def test_la_semaine_passee_ne_compte_pas(self):
        plafond, depense, _ = pilote.plafond_seance(MERCREDI, [cout(69, "2026-11-15T23:00:00+00:00")], None, REGLAGES,
                                                    {"usd_max_seance": 15})
        self.assertEqual((plafond, depense), (15, 0))


class Rapport(unittest.TestCase):
    def lire(self, contenu):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "rapport.json"
            if contenu is not None:
                chemin.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu), encoding="utf-8")
            with mock.patch.object(pilote, "RAPPORT", chemin):
                return pilote.demandes_du_rapport()

    def test_absent_ou_illisible_ne_casse_rien(self):
        self.assertEqual(self.lire(None), ("", [], []))
        self.assertEqual(self.lire("{pas du json"), ("", [], []))
        self.assertEqual(self.lire([1, 2]), ("", [], []))

    def test_demandes_completes_seulement_et_sans_mention(self):
        message, demandes, fermer = self.lire({
            "message_jules": "Fait. @quelquun",
            "demandes": [{"titre": "Créer le compte X", "quoi": "étapes", "pourquoi": "revenu", "debloque": "tout",
                          "cout": "0 €", "urgent": 1}, {"titre": "sans quoi"}, "texte"],
            "fermer": [{"numero": 12, "raison": "remplacée"}, {"numero": "abc"}, {"numero": "7"}]})
        self.assertNotIn("@quelquun", message)
        self.assertEqual([d["titre"] for d in demandes], ["Créer le compte X"])
        self.assertIs(demandes[0]["urgent"], True)
        self.assertEqual(demandes[0]["lien"], "")
        self.assertEqual([f["numero"] for f in fermer], [12, 7])


class Fermeture(unittest.TestCase):
    def test_seules_les_demandes_ouvertes_du_guichet_se_ferment(self):
        appels = []

        def gh(*args, entree=None):
            appels.append(args)
            if args[0] == "api":
                return json.dumps([
                    {"number": 5, "title": "a", "html_url": "u", "created_at": "2026-11-10", "state": "open",
                     "labels": [{"name": "guichet"}], "user": {"login": "github-actions[bot]"}},
                    {"number": 6, "title": "pr", "html_url": "u", "created_at": "2026-11-10", "state": "open",
                     "labels": [{"name": "guichet"}], "user": {"login": "github-actions[bot]"}, "pull_request": {}}])
            return ""

        fermees = pilote.fermer_demandes([{"numero": 5, "raison": "obsolète"}, {"numero": 6, "raison": "x"},
                                          {"numero": 99, "raison": "x"}], gh=gh)
        self.assertEqual(fermees, [5])
        self.assertEqual([a[:3] for a in appels if a[0] == "issue"], [("issue", "close", "5")])

    def test_rien_a_fermer_rien_a_lire(self):
        self.assertEqual(pilote.fermer_demandes([], gh=lambda *a, **k: self.fail("appel inutile")), [])


class Studio(unittest.TestCase):
    def test_un_sujet_sans_ses_cinq_fichiers_est_incomplet(self):
        with tempfile.TemporaryDirectory() as d:
            racine = Path(d)
            for f in ("sujets/lune.json", "sujets/lune.calcul.json", "public/sons/lune.wav",
                      "src/scenes/lune/index.tsx", "scripts/calcul_lune.py", "sujets/mars.json",
                      "sujets/mars.calcul.json"):
                (racine / f).parent.mkdir(parents=True, exist_ok=True)
                (racine / f).write_text("x", encoding="utf-8")
            manquants = pilote.sujets_incomplets(racine)
        self.assertEqual(manquants, ["mars (public/sons/mars.wav)", "mars (src/scenes/mars/index.tsx)",
                                     "mars (scripts/calcul_mars.py)"])


class Defaire(unittest.TestCase):
    def test_un_fichier_suivi_revient_et_un_nouveau_disparait(self):
        with tempfile.TemporaryDirectory() as d:
            git = lambda *a: subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "t")
            (Path(d) / "garde.txt").write_text("avant", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "init")
            (Path(d) / "garde.txt").write_text("après", encoding="utf-8")
            (Path(d) / "neuf").mkdir()
            (Path(d) / "neuf" / "f.py").write_text("x", encoding="utf-8")
            self.assertEqual(sorted(pilote.changements(d)), ["garde.txt", "neuf/f.py"])
            pilote.defaire(d, pilote.changements(d))
            self.assertEqual((Path(d) / "garde.txt").read_text(encoding="utf-8"), "avant")
            self.assertFalse((Path(d) / "neuf" / "f.py").exists())
            self.assertEqual(pilote.changements(d), [])


class SeanceClaude(unittest.TestCase):
    def test_seul_son_jeton_passe_et_la_sortie_est_lue(self):
        vu = {}

        def executer(commande, **k):
            vu["commande"], vu["env"] = commande, k["env"]
            return subprocess.CompletedProcess(commande, 0, json.dumps({
                "subtype": "success", "result": "fini", "total_cost_usd": 3.2, "num_turns": 40,
                "usage": {"input_tokens": 10, "output_tokens": 5}}), "")

        environ = {"CLAUDE_CODE_OAUTH_TOKEN": "a", "GH_TOKEN": "b", "GROQ_API_KEY": "c", "PATH": "/bin"}
        with mock.patch.dict("os.environ", environ, clear=True):
            r = pilote.seance_claude("consigne", 12.5, executer=executer)
        self.assertEqual((r["ok"], r["cout"], r["jetons"], r["tours"], r["erreur"]), (True, 3.2, 15, 40, None))
        self.assertEqual(set(vu["env"]) - {"CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", "PYTHONUTF8"},
                         {"CLAUDE_CODE_OAUTH_TOKEN", "PATH"})
        self.assertEqual(vu["env"]["CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"], "1")
        commande = " ".join(vu["commande"])
        for attendu in ("--max-budget-usd 12.50", "--disallowedTools Agent,Task", "--permission-mode dontAsk",
                        "--strict-mcp-config"):
            self.assertIn(attendu, commande)

    def test_une_sortie_illisible_est_un_echec_dit(self):
        executer = lambda c, **k: subprocess.CompletedProcess(c, 1, "pas du json", "plantage")
        r = pilote.seance_claude("x", 5, executer=executer)
        self.assertFalse(r["ok"])
        self.assertIn("plantage", r["erreur"])


class Message(unittest.TestCase):
    def test_dit_le_cout_et_ce_qui_n_a_pas_ete_garde(self):
        texte = pilote.message_jules({"cout_usd": 4.5, "erreur": None, "proteges_retires": ["organisation/MISSION.md"],
                                      "code_retire": [], "studio": "retiré, `npm run lint` en échec"}, "Bilan.")
        for attendu in ("4.50 $", "Bilan.", "organisation/MISSION.md", "studio ne compilait pas"):
            self.assertIn(attendu, texte)


if __name__ == "__main__":
    unittest.main()
