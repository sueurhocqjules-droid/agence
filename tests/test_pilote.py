"""Le Pilote : ce que son script garde, son budget, son rapport et son environnement.  python -m unittest discover tests"""
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from agence import pilote

MERCREDI = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)            # après le lancement
LANCEMENT = datetime(2026, 11, 18, 12, tzinfo=timezone.utc)
REGLAGES = {"claude": {"dollars_par_pourcent": 3.5, "lancement_jusqu_au": datetime(2026, 11, 20, 23, tzinfo=timezone.utc),
                       "reserve_pourcent": 15, "part_pourcent": 30},
            "emballement": {"seance_max_pourcent": 25, "echecs_identiques_max": 10, "minutes_sans_ecrire_max": 120}}


def cout(dollars, debut="2026-11-24T02:00:00+00:00"):
    return {"debut": debut, "agent": "pilote", "dollars_equiv": str(dollars), "appels_gratuits": "0"}


class Proteges(unittest.TestCase):
    def test_ce_qui_fixe_ses_limites_ou_le_controle_est_protege(self):
        for chemin in (".github/workflows/reveil.yml", "organisation/MISSION.md", "organisation/seuils.toml",
                       "organisation/autorisations.toml", "organisation/scripts.toml", "agence/pilote.py",
                       "agence/lancer.py", "agence/relecture.py", "agence/equipe.py", "agents/surete.py", "tests/test_pilote.py",
                       "agence/juge.py", "agence/tableau.py", "agence/guichet.py", "agence/registre.py", "agence/telegram.py",
                       "registre/couts.csv", "registre/revenu.jsonl", "registre/pauses.csv"):
            self.assertTrue(pilote.protege(chemin), chemin)

    def test_son_carnet_et_ses_outils_sont_a_lui(self):
        for chemin in ("registre/pilote/carnet.md", "registre/pilote/rapport.json", "agents/flux.py",
                       "organisation/rythme.toml", "organisation/PILOTE.md", "organisation/diffusion.toml",
                       "tests/test_flux.py", "agence/gabarits.py", "agence/postes.py",
                       "organisation/equipe.toml", "equipe/veille.py"):
            self.assertFalse(pilote.protege(chemin), chemin)


class Budget(unittest.TestCase):
    def test_pendant_le_lancement_seul_l_anti_emballement_borne(self):
        plafond, depense, part = pilote.plafond_seance(LANCEMENT, [cout(200, "2026-11-17T02:00:00+00:00")], None,
                                                       REGLAGES, {})
        self.assertEqual((plafond, depense, part), (87.5, 200, None))

    def test_apres_le_lancement_le_reste_de_la_part(self):
        plafond, depense, part = pilote.plafond_seance(MERCREDI, [cout(43)], None, REGLAGES, {})
        self.assertEqual((depense, part), (43, 105))
        self.assertAlmostEqual(plafond, 62)
        self.assertEqual(pilote.plafond_seance(MERCREDI, [cout(110)], None, REGLAGES, {})[0], 0)

    def test_son_propre_choix_compte_s_il_le_pose(self):
        self.assertEqual(pilote.plafond_seance(MERCREDI, [cout(10)], None, REGLAGES, {"usd_max_seance": 15})[0], 15)

    def test_la_semaine_commence_vendredi_23h(self):
        avant = cout(100, "2026-11-20T22:59:00+00:00")
        self.assertEqual(pilote.plafond_seance(MERCREDI, [avant], None, REGLAGES, {})[1], 0)
        apres = cout(100, "2026-11-20T23:00:00+00:00")
        self.assertEqual(pilote.plafond_seance(MERCREDI, [apres], None, REGLAGES, {})[1], 100)


def evt_outil(id_, nom, entree):
    return {"type": "assistant", "message": {"id": f"m{id_}", "usage": {"input_tokens": 1000, "output_tokens": 100},
                                              "content": [{"type": "tool_use", "id": id_, "name": nom, "input": entree}]}}


def evt_resultat(id_, erreur):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": id_, "is_error": erreur}]}}


def evt_limite(u):
    return {"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"seven_day": {"utilization": u}}}}


class Veille(unittest.TestCase):
    def veille(self):
        return pilote.Veille(0, REGLAGES["emballement"], 15)

    def test_dix_echecs_identiques_arretent_neuf_non(self):
        v = self.veille()
        for i in range(9):
            v.lire(evt_outil(f"a{i}", "Bash", {"command": "npm run lint"}), 1)
            self.assertIsNone(v.lire(evt_resultat(f"a{i}", True), 1))
        v.lire(evt_outil("a9", "Bash", {"command": "npm run lint"}), 1)
        self.assertIn("10 fois", v.lire(evt_resultat("a9", True), 1))

    def test_une_reussite_ou_une_autre_action_remet_a_zero(self):
        v = self.veille()
        for i in range(30):
            commande = "a" if i % 2 else "b"
            v.lire(evt_outil(f"x{i}", "Bash", {"command": commande}), 1)
            self.assertIsNone(v.lire(evt_resultat(f"x{i}", True), 1))
        v.lire(evt_outil("ok", "Bash", {"command": "b"}), 1)
        self.assertIsNone(v.lire(evt_resultat("ok", False), 1))
        self.assertEqual(v.serie, 0)

    def test_deux_heures_sans_ecrire_arretent_une_ecriture_repousse(self):
        v = self.veille()
        self.assertIsNone(v.verifier(7199))
        v.lire(evt_outil("w", "Write", {"file_path": "registre/pilote/carnet.md"}), 7000)
        self.assertIsNone(v.verifier(7300))
        self.assertIn("sans rien écrire", v.verifier(7000 + 7200))

    def test_reserve_de_jules_et_part_d_une_seance(self):
        v = self.veille()
        self.assertIsNone(v.lire(evt_limite(0.10), 1))
        self.assertIn("plus de 25%", v.lire(evt_limite(0.36), 1))
        v = self.veille()
        self.assertIsNone(v.lire(evt_limite(0.80), 1))
        self.assertIn("réserve de Jules", v.lire(evt_limite(0.85), 1))

    def test_cout_estime_par_message_sans_double_compte(self):
        v = self.veille()
        v.lire(evt_outil("a", "Read", {}), 1)
        v.lire(evt_outil("a", "Read", {}), 1)          # même message répété dans le flux
        self.assertAlmostEqual(v.cout_estime(), (1000 * 5 + 100 * 25) / 1e6)


class FauxClaude:
    """Un processus Claude Code factice qui rejoue un flux stream-json."""
    def __init__(self, evenements, code=0):
        self.stdout = iter(json.dumps(e) + "\n" for e in evenements)
        self.stdin = mock.Mock()
        self.returncode, self.code, self.tue = None, code, False

    def wait(self, timeout=None):
        self.returncode = -15 if self.tue else self.code
        return self.returncode

    def terminate(self):
        self.tue = True

    kill = terminate


class Rapport(unittest.TestCase):
    def lire(self, contenu):
        with tempfile.TemporaryDirectory() as d:
            chemin = Path(d) / "rapport.json"
            if contenu is not None:
                chemin.write_text(contenu if isinstance(contenu, str) else json.dumps(contenu), encoding="utf-8")
            with mock.patch.object(pilote, "RAPPORT", chemin):
                return pilote.lire_rapport()

    def test_absent_ou_illisible_ne_casse_rien(self):
        vide = {"message_jules": "", "demandes": [], "fermer": [], "relancer": False}
        self.assertEqual(self.lire(None), vide)
        self.assertEqual(self.lire("{pas du json"), vide)
        self.assertEqual(self.lire([1, 2]), vide)

    def test_relance_seulement_si_vrai(self):
        self.assertIs(self.lire({"relancer": True})["relancer"], True)
        self.assertIs(self.lire({"relancer": "oui"})["relancer"], False)


class Relance(unittest.TestCase):
    def passage(self, minutes, **k):
        return {"debut": "2026-11-18T01:00:00+00:00",
                "fin": f"2026-11-18T{1 + minutes // 60:02d}:{minutes % 60:02d}:00+00:00",
                "relancer": True, "erreur": None} | k

    def test_seulement_apres_une_seance_saine_d_au_moins_10_minutes(self):
        self.assertTrue(pilote.relancer(self.passage(45)))
        self.assertFalse(pilote.relancer(self.passage(5)))
        self.assertFalse(pilote.relancer(self.passage(45, erreur="arrêt anti-emballement : x")))
        self.assertFalse(pilote.relancer(self.passage(45, relancer=False)))


class Appliquer(unittest.TestCase):
    def test_le_patch_passe_sans_les_chemins_interdits(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as ailleurs:
            def git(*a):
                return subprocess.run(["git", "-C", d, *a], check=True, capture_output=True)
            git("init", "-q")
            git("config", "user.email", "t@t")
            git("config", "user.name", "t")
            for f in ("organisation/MISSION.md", "agents/flux.py"):
                (Path(d) / f).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / f).write_text("avant\n", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "init")
            for f in ("organisation/MISSION.md", "agents/flux.py"):
                (Path(d) / f).write_text("après\n", encoding="utf-8")
            (Path(d) / "agence").mkdir()
            (Path(d) / "agence" / "pilote.py").write_text("pirate\n", encoding="utf-8")
            git("add", "-A")
            patch = Path(ailleurs) / "agence.patch"
            patch.write_bytes(git("diff", "--cached", "--binary").stdout)
            git("reset", "-q", "--hard")
            git("clean", "-qfd")
            remis = pilote.appliquer(d, patch, pilote.protege)
            self.assertEqual(sorted(remis), ["agence/pilote.py", "organisation/MISSION.md"])
            self.assertEqual((Path(d) / "agents/flux.py").read_text(encoding="utf-8"), "après\n")
            self.assertEqual((Path(d) / "organisation/MISSION.md").read_text(encoding="utf-8"), "avant\n")
            self.assertFalse((Path(d) / "agence" / "pilote.py").exists())


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
    def lancer(self, evenements, code=0):
        vu = {}

        def ouvrir(commande, **k):
            vu["commande"], vu["env"] = commande, k["env"]
            vu["proc"] = FauxClaude(evenements, code)
            return vu["proc"]

        environ = {"CLAUDE_CODE_OAUTH_TOKEN": "a", "GH_TOKEN": "b", "GROQ_API_KEY": "c", "PATH": "/bin"}
        with mock.patch.dict("os.environ", environ, clear=True):
            r = pilote.seance_claude("consigne", 12.5, pilote.Veille(0, REGLAGES["emballement"], 15),
                                     ouvrir=ouvrir, horloge=lambda: 1)
        return r, vu

    def test_seul_son_jeton_passe_et_le_resultat_est_lu(self):
        r, vu = self.lancer([{"type": "system"}, evt_limite(0.2),
                             {"type": "result", "subtype": "success", "result": "fini", "total_cost_usd": 3.2,
                              "num_turns": 40, "usage": {"input_tokens": 10, "output_tokens": 5}}])
        self.assertEqual((r["ok"], r["cout"], r["jetons"], r["tours"], r["erreur"], r["utilisation"]),
                         (True, 3.2, 15, 40, None, 0.2))
        self.assertNotIn("GH_TOKEN", vu["env"])
        self.assertNotIn("GROQ_API_KEY", vu["env"])
        self.assertEqual(vu["env"]["CLAUDE_CODE_OAUTH_TOKEN"], "a")
        commande = " ".join(vu["commande"])
        for attendu in ("--max-budget-usd", "stream-json", "--verbose", "Agent"):
            self.assertIn(attendu, commande)
        self.assertNotIn("--disallowedTools", commande)

    def test_un_emballement_tue_la_seance_et_estime_son_cout(self):
        evenements = []
        for i in range(12):
            evenements += [evt_outil(f"b{i}", "Bash", {"command": "x"}), evt_resultat(f"b{i}", True)]
        r, vu = self.lancer(evenements)
        self.assertTrue(vu["proc"].tue)
        self.assertFalse(r["ok"])
        self.assertIn("anti-emballement", r["erreur"])
        self.assertGreater(r["cout"], 0)

    def test_une_sortie_sans_resultat_est_un_echec_dit(self):
        r, _ = self.lancer([], code=1)
        self.assertFalse(r["ok"])
        self.assertTrue(r["erreur"])


class Message(unittest.TestCase):
    def test_dit_le_cout_et_ce_qui_n_a_pas_ete_garde(self):
        texte = pilote.message_jules({"cout_usd": 4.5, "erreur": None, "proteges_retires": ["organisation/MISSION.md"],
                                      "code_retire": [], "studio": "retiré, `npm run lint` en échec"}, "Bilan.")
        for attendu in ("4.50 $", "Bilan.", "organisation/MISSION.md", "studio ne compilait pas"):
            self.assertIn(attendu, texte)


if __name__ == "__main__":
    unittest.main()
