"""Ingénierie : qui peut demander, ce que reçoit Claude, quand la PR est fusionnée seule.

python -m unittest discover tests
"""
import json
import os
import re
import subprocess
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from agence import ingenierie, organisation, protege
from agents import direction

RACINE = Path(__file__).resolve().parent.parent
WORKFLOW = (RACINE / ".github" / "workflows" / "ingenierie.yml").read_text(encoding="utf-8")
VERT = dict(tests="success", banc="skipped", banc_demande=False, controle="success", protege="false", verdict="ok")


def demande(**k):
    return {"numero": 12, "titre": "Ajouter un test", "texte": "Quoi : un test", "auteur": ingenierie.JULES,
            "etiquettes": ["ingenierie"], "ouverte": True, "pr": False} | k


class Demande(unittest.TestCase):
    def test_seules_les_demandes_de_jules_ou_de_l_agence_comptent(self):
        self.assertIsNone(ingenierie.refus_demande(demande()))
        self.assertIsNone(ingenierie.refus_demande(demande(auteur="github-actions[bot]")))
        self.assertIn("inconnu", ingenierie.refus_demande(demande(auteur="inconnu")))
        self.assertTrue(ingenierie.refus_demande(demande(etiquettes=["guichet"])))
        self.assertTrue(ingenierie.refus_demande(demande(ouverte=False)))
        self.assertTrue(ingenierie.refus_demande(demande(pr=True)))

    def test_une_demande_d_agent_cree_l_issue_puis_lance_le_workflow(self):
        appels = []

        def gh(*args, entree=None):
            appels.append((args, entree))
            return "https://github.com/x/agence/issues/31\n"
        with mock.patch.object(ingenierie, "_gh", gh), mock.patch.dict(os.environ, {"AGENCE_ESSAI": "0"}):
            self.assertEqual(ingenierie.demander("Réparer @x", "quoi", "pourquoi", "la Direction", "preuve"), 31)
        (creation, corps), (lancement, _) = appels
        self.assertEqual(creation[:2], ("issue", "create"))
        self.assertIn(ingenierie.ETIQUETTE, creation)
        self.assertNotIn("@", " ".join(creation) + corps)
        self.assertEqual(lancement[:3], ("workflow", "run", "ingenierie.yml"))
        self.assertIn("issue=31", lancement)

    def test_en_essai_rien_ne_part(self):
        with mock.patch.object(ingenierie, "_gh", side_effect=AssertionError("appel interdit en essai")), \
                mock.patch.dict(os.environ, {"AGENCE_ESSAI": "1"}), mock.patch("builtins.print"):
            self.assertIsNone(ingenierie.demander("t", "q", "p", "la Direction"))

    def test_un_lancement_refuse_ne_perd_pas_la_demande(self):
        def gh(*args, entree=None):
            if args[0] == "workflow":
                raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403")
            return "https://github.com/x/agence/issues/7\n"
        with mock.patch.object(ingenierie, "_gh", gh), mock.patch.dict(os.environ, {"AGENCE_ESSAI": "0"}), \
                mock.patch("builtins.print"):
            self.assertEqual(ingenierie.demander("t", "q", "p", "x"), 7)


class Seance(unittest.TestCase):
    def lancer(self, sortie, code=0, env=None, isolee=False):
        vu = {}

        def executer(commande, **k):
            vu.update(commande=commande, **k)
            return subprocess.CompletedProcess(commande, code, stdout=sortie, stderr="")
        with mock.patch.dict(os.environ, env or {}):
            return ingenierie.seance("consigne", 1.5, "/tmp/travail", executer, isolee), vu

    def test_l_isolation_n_est_demandee_que_si_la_machine_la_permet(self):
        ok = json.dumps({"result": "fait", "subtype": "success"})
        self.assertEqual(self.lancer(ok, isolee=True)[1]["env"].get("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB"), "1")
        self.assertNotIn("CLAUDE_CODE_SUBPROCESS_ENV_SCRUB", self.lancer(ok, isolee=False)[1]["env"])
        demarre = lambda *a, **k: subprocess.CompletedProcess(a, 0)   # noqa: E731
        refuse = lambda *a, **k: subprocess.CompletedProcess(a, 1)    # noqa: E731
        with mock.patch.object(ingenierie.shutil, "which", lambda nom: f"/usr/bin/{nom}"):
            self.assertTrue(ingenierie.isolation_possible(demarre))
            self.assertFalse(ingenierie.isolation_possible(refuse))   # AppArmor qui bloque bwrap, par exemple
        with mock.patch.object(ingenierie.shutil, "which", lambda nom: None if nom == "socat" else "/usr/bin/bwrap"):
            self.assertFalse(ingenierie.isolation_possible(demarre))

    def test_claude_ne_recoit_que_son_jeton_et_des_plafonds(self):
        s, vu = self.lancer(json.dumps({"result": "fait", "total_cost_usd": 0.42, "num_turns": 9, "subtype": "success",
                                        "usage": {"input_tokens": 10, "output_tokens": 5}}),
                            env={"CLAUDE_CODE_OAUTH_TOKEN": "c", "GH_TOKEN": "g", "GEMINI_API_KEY": "k",
                                 "TELEGRAM_BOT_TOKEN": "t"})
        self.assertEqual((s["ok"], s["cout"], s["jetons"], s["resume"]), (True, 0.42, 15, "fait"))
        self.assertEqual(vu["env"].get("CLAUDE_CODE_OAUTH_TOKEN"), "c")
        for cle in ("GH_TOKEN", "GEMINI_API_KEY", "TELEGRAM_BOT_TOKEN"):
            self.assertNotIn(cle, vu["env"])
        c = vu["commande"]
        self.assertEqual(c[c.index("--max-turns") + 1], str(ingenierie.TOURS_MAX))
        self.assertEqual(c[c.index("--max-budget-usd") + 1], "1.50")
        self.assertEqual(c[c.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(vu["cwd"], "/tmp/travail")
        self.assertEqual(vu["timeout"], ingenierie.DUREE_MAX_S)

    def test_la_seule_commande_permise_est_celle_des_tests(self):
        commandes = re.findall(r"Bash\(([^)]*)\)", ingenierie.PERMIS)
        self.assertTrue(commandes)
        for commande in commandes:
            self.assertTrue(commande.startswith("python -m unittest"), commande)
        self.assertNotIn("Bash,", ingenierie.PERMIS + ",")   # jamais Bash sans filtre
        self.assertNotIn("Web", ingenierie.OUTILS)
        self.assertNotIn("claude", ingenierie.PERMIS.lower())

    def test_un_arret_de_claude_garde_le_cout(self):
        s, _ = self.lancer(json.dumps({"is_error": True, "subtype": "error_max_turns", "total_cost_usd": 2.1}), code=1)
        self.assertEqual((s["ok"], s["cout"]), (False, 2.1))
        self.assertIn("error_max_turns", s["erreur"])
        s, _ = self.lancer("pas du json", code=1)
        self.assertEqual((s["ok"], s["cout"]), (False, 0.0))

    def test_une_seance_trop_longue_est_un_echec(self):
        def executer(commande, **k):
            raise subprocess.TimeoutExpired(commande, k["timeout"])
        self.assertFalse(ingenierie.seance("c", 1, ".", executer, False)["ok"])

    def test_la_consigne_porte_la_fiche_et_la_demande(self):
        texte = ingenierie.consigne(demande(texte="Ajoute tests/test_x.py"))
        self.assertIn("Ajoute tests/test_x.py", texte)
        self.assertIn("Demande #12", texte)
        self.assertIn("jamais en modifier", texte)          # consignes de la fiche
        self.assertIn("Aucune commande git", texte)

    def test_le_plafond_suit_le_reste_de_la_semaine(self):
        maintenant = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
        couts = [{"agent": "ingenierie", "debut": "2026-11-13T10:00:00+00:00", "dollars_equiv": "2.5"},
                 {"agent": "ingenierie", "debut": "2026-11-06T10:00:00+00:00", "dollars_equiv": "5"},
                 {"agent": "direction", "debut": "2026-11-13T10:00:00+00:00", "dollars_equiv": "4"}]
        self.assertEqual(ingenierie.reste_semaine(maintenant, couts, 9), 6.5)

    def test_la_fiche_plafonne_le_poste(self):
        fiche = organisation.fiches()["ingenierie"]
        self.assertGreater(fiche["budget"]["claude_usd_semaine"], 0)
        self.assertLessEqual(ingenierie.USD_PAR_LANCEMENT, fiche["budget"]["claude_usd_semaine"])
        self.assertEqual(set(fiche["env"]), {"CLAUDE_CODE_OAUTH_TOKEN", "GH_TOKEN"})
        self.assertIn("## Pourquoi ce poste existe", (RACINE / "organisation/postes/ingenierie.md").read_text(encoding="utf-8"))


class Decision(unittest.TestCase):
    def test_fusion_seulement_si_tout_est_vert(self):
        self.assertEqual(ingenierie.decision(**VERT), ("fusion", []))
        self.assertEqual(ingenierie.decision(**VERT | {"banc_demande": True, "banc": "success"}), ("fusion", []))
        for cle, valeur in (("tests", "failure"), ("tests", ""), ("tests", "skipped"), ("verdict", "a_revoir"),
                            ("verdict", "inconnu"), ("verdict", ""), ("controle", "failure"), ("protege", ""),
                            ("protege", "n'importe quoi")):
            with self.subTest(cle=cle, valeur=valeur):
                choix, raisons = ingenierie.decision(**VERT | {cle: valeur})
                self.assertEqual(choix, "ouverte")
                self.assertTrue(raisons)

    def test_le_banc_compte_quand_un_agent_est_touche(self):
        for banc in ("failure", "skipped", ""):
            self.assertEqual(ingenierie.decision(**VERT | {"banc_demande": True, "banc": banc})[0], "ouverte")
        self.assertTrue(ingenierie.banc_requis(["agents/flux.py"]))
        self.assertTrue(ingenierie.banc_requis(["README.md", "organisation/postes/veilleur.md"]))
        self.assertTrue(ingenierie.banc_requis(["organisation/MISSION.md"]))
        self.assertFalse(ingenierie.banc_requis(["tests/test_x.py", "README.md", "organisation/diffusion.toml"]))

    def test_le_banc_couvre_les_memes_chemins_que_banc_yml(self):
        texte = (RACINE / ".github" / "workflows" / "banc.yml").read_text(encoding="utf-8")
        chemins = {c.replace("/**", "/") for c in re.findall(r'- "([^"]+)"', texte)} - {".github/workflows/banc.yml"}
        self.assertEqual(chemins, set(ingenierie.BANC_SUR))

    def test_un_fichier_protege_attend_jules_meme_avec_son_accord(self):
        sans_accord = VERT | {"protege": "true", "controle": "failure"}
        avec_accord = VERT | {"protege": "true", "controle": "success"}
        self.assertEqual(ingenierie.decision(**sans_accord)[0], "jules")
        self.assertEqual(ingenierie.decision(**avec_accord)[0], "jules")

    def conclure(self, **env):
        appels = []
        env = {f"INGENIERIE_{k.upper()}": v for k, v in
               (dict(tests="success", banc="skipped", banc_demande="false", controle="success", protege="false",
                     verdict="ok", sha="abc", issue="12") | env).items()}
        with mock.patch.object(ingenierie, "_gh", lambda *a, entree=None: appels.append(a) or ""), \
                mock.patch.object(ingenierie.subprocess, "run", lambda *a, **k: appels.append(tuple(a[0][1:]))), \
                mock.patch.object(ingenierie.registre, "decider", lambda *a, **k: appels.append(("decision", *a))), \
                mock.patch.object(ingenierie.lancer, "noter_journal", lambda *a: appels.append(("journal", *a))), \
                mock.patch.dict(os.environ, {"GITHUB_OUTPUT": "", "GITHUB_STEP_SUMMARY": ""}), \
                mock.patch("builtins.print"):
            return ingenierie.conclure("40", env), appels

    def test_la_fusion_vise_le_commit_controle_et_ferme_la_demande(self):
        choix, appels = self.conclure()
        self.assertEqual(choix, "fusion")
        fusion = next(a for a in appels if a[:2] == ("pr", "merge"))
        self.assertEqual(fusion[fusion.index("--match-head-commit") + 1], "abc")
        self.assertTrue([a for a in appels if a[:3] == ("issue", "close", "12")])
        self.assertTrue([a for a in appels if a[0] == "decision"])

    def test_sans_vert_rien_n_est_fusionne_et_le_blocage_est_note(self):
        for env in ({"tests": "failure"}, {"verdict": "inconnu"}, {"protege": "true", "controle": "failure"}):
            with self.subTest(env=env):
                choix, appels = self.conclure(**env)
                self.assertNotEqual(choix, "fusion")
                self.assertFalse([a for a in appels if a[:2] == ("pr", "merge")])
                self.assertTrue([a for a in appels if a[0] == "journal" and a[2].get("bloquant")])

    def test_l_ingenierie_ne_pose_jamais_l_accord_de_jules(self):
        _, appels = self.conclure(protege="true", controle="failure")
        etiquettes = [a[a.index("--add-label") + 1] for a in appels if "--add-label" in a]
        self.assertEqual(etiquettes, [ingenierie.GUICHET])
        source = (RACINE / "agence" / "ingenierie.py").read_text(encoding="utf-8")
        self.assertNotIn(f'"{protege.ACCORD}"', source)
        self.assertNotIn("add-label\", \"accord", source)


class Protection(unittest.TestCase):
    def test_l_ingenierie_ne_peut_pas_se_modifier_seule(self):
        for chemin in ("agence/ingenierie.py", "organisation/postes/ingenierie.md", ".github/workflows/ingenierie.yml"):
            self.assertTrue(protege.raison(chemin, "modified"), chemin)

    def test_le_workflow_decide_avec_le_code_de_main(self):
        self.assertIn("ref: ${{ github.event.repository.default_branch }}", WORKFLOW)
        self.assertEqual(WORKFLOW.count("actions/checkout"), 1)      # la PR n'est jamais extraite à la place de main
        self.assertNotIn("pull_request", WORKFLOW.split("jobs:")[0])  # ni pull_request ni pull_request_target
        for ligne in re.findall(r"run: .*", WORKFLOW):                # rien d'une issue ou d'une PR dans une commande
            self.assertNotIn("${{", ligne)

    def test_une_etiquette_ne_lance_que_posee_par_jules(self):
        self.assertIn("github.event.sender.login == 'sueurhocqjules-droid'", WORKFLOW)
        self.assertIn("github.event.label.name == 'ingenierie'", WORKFLOW)

    def test_le_code_de_la_pr_tourne_sans_jeton_github_ni_claude(self):
        etapes = re.split(r"\n      - ", WORKFLOW)
        self.assertNotIn("working-directory: ${{ runner.temp }}/travail", WORKFLOW)   # jamais dans le dossier de Claude
        dans_la_copie = [e for e in etapes if "working-directory: ${{ runner.temp }}/pr" in e]
        self.assertGreaterEqual(len(dans_la_copie), 2)   # tests et banc
        for etape in dans_la_copie:
            self.assertNotIn("github.token", etape)
            self.assertNotIn("CLAUDE_CODE_OAUTH_TOKEN", etape)
            self.assertNotIn("TELEGRAM", etape)
        claude = [e for e in etapes if "CLAUDE_CODE_OAUTH_TOKEN" in e]
        self.assertEqual(len(claude), 1)
        self.assertIn("python -m agence.lancer ingenierie construire", claude[0])   # pause et budget par le lanceur

    def test_le_workflow_n_a_pas_plus_de_droits_que_necessaire(self):
        droits = re.search(r"\npermissions:\n((?:  .*\n)+)", WORKFLOW).group(1)
        self.assertEqual(set(re.findall(r"^  ([a-z-]+): ", droits, re.MULTILINE)), {"contents", "pull-requests", "issues"})
        self.assertNotIn("secrets.TELEGRAM", WORKFLOW)
        self.assertNotIn("YT_TOKEN", WORKFLOW)
        self.assertNotIn("META_TOKEN", WORKFLOW)


class Operations(unittest.TestCase):
    def test_un_declenchement_refuse_par_github_sur_une_pr_de_l_ingenierie_n_est_pas_une_panne(self):
        from agents import chef_operations
        self.assertTrue(ingenierie.PREFIXE.startswith(chef_operations.BRANCHES_INGENIERIE))
        refuse = {"workflowName": "Mises à jour", "conclusion": "failure", "createdAt": "2026-11-14T01:17:22Z",
                  "url": "u1", "event": "pull_request", "headBranch": "ingenierie/demande-9-1"}
        vraie = refuse | {"headBranch": "dependabot/pip/x", "url": "u2"}
        ok = {"workflowName": "Ingénierie", "conclusion": "success", "createdAt": "2026-11-14T01:16:40Z", "url": "u3",
              "event": "issues", "headBranch": "main"}
        c = chef_operations.chiffres([refuse, vraie, ok], [])
        self.assertEqual(c["reveils_par_workflow"], {"Ingénierie": "1/1", "Mises à jour": "0/1"})
        self.assertEqual([p["lien"] for p in c["pannes_sans_trace"]], ["u2"])


class Direction(unittest.TestCase):
    def test_la_direction_peut_ecrire_a_l_ingenierie(self):
        s = direction.schema(["chef-contenu"])
        self.assertIn("ingenierie", s["required"])
        self.assertEqual(s["properties"]["ingenierie"]["maxItems"], ingenierie.DEMANDES_MAX)
        self.assertIn("ingenierie", direction.consigne_systeme())

    def test_sa_demande_devient_une_issue_et_une_decision(self):
        reponse = {"decisions": [], "retours": [], "consignes": [], "questions": [], "investissements": [],
                   "ingenierie": [{"titre": "Réparer le relevé", "quoi": "q", "pourquoi": "p", "preuve": "run 1"}] * 3}
        demandes, notes = [], []
        with mock.patch.object(direction.ingenierie, "demander", lambda *a: demandes.append(a) or 31), \
                mock.patch.object(direction.registre, "decider", lambda *a, **k: notes.append(a)):
            faits, refus = direction.appliquer(reponse, datetime(2026, 11, 15, tzinfo=timezone.utc), {})
        self.assertEqual(len(demandes), ingenierie.DEMANDES_MAX)
        self.assertEqual(refus, [])
        self.assertIn("issue #31", notes[0][1])
        self.assertTrue(all("Ingénierie" in f for f in faits))

    def test_une_demande_qui_echoue_est_notee_sans_arreter_la_seance(self):
        reponse = {"decisions": [], "retours": [], "consignes": [], "questions": [], "investissements": [],
                   "ingenierie": [{"titre": "t", "quoi": "q", "pourquoi": "p", "preuve": ""}]}

        def panne(*a):
            raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403")
        with mock.patch.object(direction.ingenierie, "demander", panne), \
                mock.patch.object(direction.registre, "decider", lambda *a, **k: None):
            faits, refus = direction.appliquer(reponse, datetime(2026, 11, 15, tzinfo=timezone.utc), {})
        self.assertEqual(faits, [])
        self.assertIn("403", refus[0])


if __name__ == "__main__":
    unittest.main()
