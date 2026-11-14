"""Fichiers protégés (règle 9) : ce que le contrôle refuse, qui peut donner l'accord, relecture en sortie fermée.

python -m unittest discover tests
"""
import re
import unittest
from pathlib import Path

from agence import protege, relecture
from agents import chef_operations

RACINE = Path(__file__).resolve().parent.parent


class Controle(unittest.TestCase):
    def test_refuse_les_fichiers_toujours_proteges(self):
        for chemin in (".github/workflows/reveil.yml", ".github/CODEOWNERS", "organisation/MISSION.md",
                       "organisation/autorisations.toml", "agence/protege.py", "agence/relecture.py",
                       "agence/banc_agents.py", "agence/ingenierie.py", "organisation/postes/ingenierie.md"):
            for statut in ("modified", "added", "removed"):
                with self.subTest(chemin=chemin, statut=statut):
                    self.assertTrue(protege.raison(chemin, statut))

    def test_un_test_ou_un_cas_existant_ne_change_pas_mais_on_peut_en_ajouter(self):
        for chemin in ("tests/test_flux.py", "tests/donnees/x.json", "banc/agents/direction-blocage-leve.json"):
            with self.subTest(chemin=chemin):
                self.assertTrue(protege.raison(chemin, "modified"))
                self.assertTrue(protege.raison(chemin, "removed"))
                self.assertIsNone(protege.raison(chemin, "added"))

    def test_un_renommage_ne_sort_pas_un_fichier_de_la_protection(self):
        self.assertTrue(protege.raison("ailleurs/test_flux.py", "renamed", "tests/test_flux.py"))
        self.assertTrue(protege.raison("tests/nouveau.py", "renamed", "agents/flux.py"))   # dans le doute : refus
        self.assertTrue(protege.raison("agence/x.py", "renamed", ".github/workflows/reveil.yml"))

    def test_le_code_des_agents_est_libre(self):
        fichiers = [("agents/flux.py", "modified", ""), ("organisation/postes/flux.md", "modified", ""),
                    ("organisation/diffusion.toml", "modified", ""), ("tests/test_nouveau.py", "added", ""),
                    ("README.md", "modified", ""), ("agence/protege_bis.py", "added", "")]
        self.assertEqual(protege.refus(fichiers), [])

    def test_une_raison_par_fichier_protege(self):
        fichiers = [("agents/flux.py", "modified", ""), ("tests/test_flux.py", "modified", ""),
                    (".github/workflows/x.yml", "added", "")]
        self.assertEqual(len(protege.refus(fichiers)), 2)

    def test_l_accord_ne_vaut_que_pose_par_jules_et_toujours_en_place(self):
        J, bot = protege.JULES, "github-actions[bot]"
        self.assertFalse(protege.accord([]))
        self.assertTrue(protege.accord([("labeled", "accord-jules", J)]))
        self.assertFalse(protege.accord([("labeled", "accord-jules", bot)]))
        self.assertFalse(protege.accord([("labeled", "accord-jules", J), ("unlabeled", "accord-jules", J)]))
        self.assertFalse(protege.accord([("labeled", "accord-jules", J), ("unlabeled", "accord-jules", bot),
                                         ("labeled", "accord-jules", bot)]))
        self.assertFalse(protege.accord([("labeled", "valide", J)]))
        self.assertTrue(protege.accord([("labeled", "accord-jules", J), ("labeled", "urgent", bot)]))

    def test_codeowners_couvre_la_meme_liste(self):
        lignes = (RACINE / ".github" / "CODEOWNERS").read_text(encoding="utf-8").splitlines()
        couverts = {l.split()[0].lstrip("/") for l in lignes if l.strip() and not l.startswith("#")}
        self.assertEqual(couverts, set(protege.TOUJOURS) | set(protege.EXISTANTS))

    def test_le_workflow_ne_lance_jamais_le_code_de_la_pr(self):
        texte = (RACINE / ".github" / "workflows" / "protege.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request_target", texte)
        self.assertEqual(texte.count("ref: ${{ github.event.repository.default_branch }}"), texte.count("actions/checkout"))
        self.assertNotIn("head.sha", texte)
        self.assertNotIn("head.ref", texte)
        for ligne in re.findall(r"run: .*", texte):   # rien de la PR interpolé dans une commande
            self.assertNotIn("${{", ligne)

    def test_les_controles_refuses_ne_comptent_pas_comme_pannes(self):
        runs = [{"workflowName": "Fichiers protégés", "conclusion": "failure", "createdAt": "2026-11-10T11:17:00Z",
                 "url": "u1"},
                {"workflowName": "Réveil", "conclusion": "success", "createdAt": "2026-11-10T05:17:00Z", "url": "u2"}]
        c = chef_operations.chiffres(runs, [])
        self.assertEqual((c["reveils_reussis_pourcent"], c["pannes_sans_trace"]), (100, []))


class Relecture(unittest.TestCase):
    def test_sortie_fermee(self):
        self.assertEqual(relecture.valider({"verdict": "parfait"})["verdict"], "inconnu")
        self.assertEqual(relecture.valider(None)["verdict"], "inconnu")
        self.assertEqual(relecture.valider("ok")["verdict"], "inconnu")
        lu = relecture.valider({"verdict": "ok", "resume": "rien", "risques": []})
        self.assertEqual((lu["verdict"], lu["risques"]), ("ok", []))

    def test_un_ok_avec_des_risques_est_a_revoir_et_les_risques_sont_bornes(self):
        risques = [{"fichier": f"f{i}", "raison": "r"} for i in range(9)] + ["texte", {"fichier": "x"}]
        lu = relecture.valider({"verdict": "ok", "resume": "x", "risques": risques})
        self.assertEqual((lu["verdict"], len(lu["risques"])), ("a_revoir", relecture.RISQUES_MAX))

    def test_le_commentaire_ne_mentionne_personne(self):
        lu = relecture.valider({"verdict": "a_revoir", "resume": "voir @jules <script>",
                                "risques": [{"fichier": "a`b", "raison": "@x\nligne"}]})
        texte = relecture.commentaire(lu, "gemini-flash-lite-latest")
        self.assertNotIn("@", texte)
        self.assertNotIn("<script>", texte)
        self.assertIn("`a'b` : (a)x ligne", texte)

    def test_relecteur_injoignable_ou_hors_format(self):
        def muet(*a, **k):
            raise RuntimeError("aucun modèle")
        self.assertEqual(relecture.relire("t", "diff", muet)[0]["verdict"], "inconnu")
        avis, modele = relecture.relire("t", "diff", lambda *a, **k: ("pas de json", "m", 0, 0, 0))
        self.assertEqual((avis["verdict"], modele), ("inconnu", "m"))
        avis, _ = relecture.relire("t", "x" * (relecture.DIFF_MAX + 10),
                                   lambda p, c, **k: ('{"verdict": "ok", "resume": "' + str("tronqué" in c) + '"}', "m", 0, 0, 0))
        self.assertEqual(avis, {"verdict": "ok", "resume": "True", "risques": []})

    def test_le_relecteur_n_est_jamais_claude(self):
        from agence import postes
        self.assertTrue(postes.POSTES["relecteur-pr"])
        self.assertFalse([m for _, m, _ in postes.POSTES["relecteur-pr"] if "claude" in m.lower()])


if __name__ == "__main__":
    unittest.main()
