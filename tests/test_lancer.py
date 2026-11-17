"""Tests du lanceur : pause, budget, cloisonnement des secrets, hiérarchie.  python -m unittest discover tests"""
import unittest
from datetime import datetime, timezone

from agence import lancer, organisation

POSTES = {
    "direction": {"id": "direction", "superieur": "jules"},
    "chef-contenu": {"id": "chef-contenu", "superieur": "direction"},
    "auteur": {"id": "auteur", "superieur": "chef-contenu", "module": "x", "budget": {"claude_usd_semaine": 30}},
}
LUNDI = datetime(2026, 11, 9, tzinfo=timezone.utc)
MERCREDI = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)


def cout(agent, quand, dollars=0, appels=0):
    return {"agent": agent, "debut": quand.isoformat(), "dollars_equiv": str(dollars), "appels_gratuits": str(appels)}


def ligne_pause(cible, action):
    return {"cible": cible, "action": action, "par": "surete", "raison": "essai"}


class Pause(unittest.TestCase):
    cibles = ["auteur", "chef-contenu", "direction", "tout"]

    def test_pause_du_chef_bloque_son_equipe(self):
        self.assertIsNotNone(lancer.pause_active(self.cibles, [ligne_pause("chef-contenu", "pause")]))

    def test_reprise_leve_la_pause(self):
        pauses = [ligne_pause("auteur", "pause"), ligne_pause("auteur", "reprise")]
        self.assertIsNone(lancer.pause_active(self.cibles, pauses))

    def test_pause_generale(self):
        self.assertIsNotNone(lancer.pause_active(self.cibles, [ligne_pause("tout", "pause")]))

    def test_pause_d_une_autre_equipe_sans_effet(self):
        self.assertIsNone(lancer.pause_active(self.cibles, [ligne_pause("chef-recherche", "pause")]))


class Budget(unittest.TestCase):
    budget = {"claude_usd_semaine": 30, "appels_gratuits_jour": 20}

    def test_sous_le_budget(self):
        couts = [cout("auteur", LUNDI, dollars=14.2)]
        self.assertIsNone(lancer.budget_atteint("auteur", self.budget, couts, MERCREDI))

    def test_budget_semaine_atteint(self):
        couts = [cout("auteur", LUNDI, dollars=14.2), cout("auteur", MERCREDI, dollars=16)]
        self.assertIn("semaine", lancer.budget_atteint("auteur", self.budget, couts, MERCREDI))

    def test_semaine_precedente_ignoree(self):
        couts = [cout("auteur", datetime(2026, 11, 8, 23, tzinfo=timezone.utc), dollars=50)]
        self.assertIsNone(lancer.budget_atteint("auteur", self.budget, couts, MERCREDI))

    def test_appels_du_jour(self):
        couts = [cout("auteur", MERCREDI, appels=20)]
        self.assertIn("appels", lancer.budget_atteint("auteur", self.budget, couts, MERCREDI))

    def test_couts_d_un_autre_agent_ignores(self):
        couts = [cout("direction", MERCREDI, dollars=100)]
        self.assertIsNone(lancer.budget_atteint("auteur", self.budget, couts, MERCREDI))


class BloquantEchec(unittest.TestCase):
    def test_garde_les_20_dernieres_lignes(self):
        texte = lancer.bloquant_echec("flux", 1, [f"ligne {i}" for i in range(30)])
        self.assertIn("code 1", texte)
        self.assertIn("ligne 29", texte)
        self.assertIn("ligne 10", texte)
        self.assertNotIn("ligne 9\n", texte + "\n")
        self.assertNotIn("voir la sortie", texte)

    def test_sortie_vide_le_dit(self):
        self.assertIn("sortie vide", lancer.bloquant_echec("flux", 2, []))


class Secrets(unittest.TestCase):
    def test_seuls_les_secrets_declares_passent(self):
        env = {"YT_TOKEN_EN": "a", "GH_TOKEN": "b", "GROQ_API_KEY": "c", "PATH": "/bin", "RENDU_DIR": "rendu"}
        self.assertEqual(lancer.env_cloisonne(env, {"YT_TOKEN_EN"}),
                         {"YT_TOKEN_EN": "a", "PATH": "/bin", "RENDU_DIR": "rendu"})


class Hierarchie(unittest.TestCase):
    def test_chaine(self):
        self.assertEqual(organisation.chaine_de_commandement("auteur", POSTES), ["auteur", "chef-contenu", "direction"])

    def test_boucle_refusee(self):
        with self.assertRaises(ValueError):
            organisation.chaine_de_commandement("a", {"a": {"superieur": "b"}, "b": {"superieur": "a"}})

    def test_vraies_fiches_coherentes(self):
        postes = organisation.fiches()
        for agent in postes:
            organisation.chaine_de_commandement(agent, postes)
        for nom, s in organisation.scripts().items():
            self.assertIn(s["proprietaire"], postes, nom)

    def test_agent_non_construit_refuse(self):
        with self.assertRaises(ValueError):
            lancer.preparer("direction", POSTES, {})


class CauseDEchec(unittest.TestCase):
    """Chaque panne vue devient un cas : la catégorie écrite dans « bloquant » doit être la bonne."""
    CAS = {
        "quota ou 429": ["appel", "HTTP 429 Too Many Requests"],
        "limite de 5 h": ["Claude usage limit reached", "your 5-hour limit resets at 3am"],
        "tours épuisés": ["claude s'est arrêté (error_max_turns) : "],
        "conflit": ["CONFLICT (content): Merge conflict in agence/x.py"],
        "tests": ["FAIL: test_a (tests.test_x.T)", "FAILED (failures=1)"],
        "autre": ["Traceback", "KeyError: 'x'"],
    }

    def test_chaque_categorie(self):
        for attendue, lignes in self.CAS.items():
            with self.subTest(attendue):
                self.assertEqual(lancer.categorie_echec(lignes), attendue)

    def test_bloquant_garde_la_categorie_et_20_lignes(self):
        sortie = [f"ligne {i}" for i in range(30)] + ["HTTP 429"]
        texte = lancer.bloquant_echec("ingenierie", 1, sortie)
        self.assertIn("code 1", texte)
        self.assertIn("quota ou 429", texte)
        self.assertEqual(len(texte.splitlines()), 1 + 20)
        self.assertNotIn("ligne 5\n", texte)


class CauseEchec(unittest.TestCase):
    def test_derniere_ligne_utile_d_une_trace(self):
        lignes = ["Traceback (most recent call last):", '  File "x.py", line 1, in f', "    return run(...)",
                  "           ~~~~^^^^", "subprocess.CalledProcessError: Command 'git' returned non-zero exit status 1.",
                  "                             ^^^^"]
        self.assertEqual(lancer.cause_echec(lignes),
                         "subprocess.CalledProcessError: Command 'git' returned non-zero exit status 1.")

    def test_message_de_git_garde(self):
        self.assertEqual(lancer.cause_echec(["git push a échoué : remote: Permission denied"]),
                         "git push a échoué : remote: Permission denied")

    def test_sortie_vide(self):
        self.assertEqual(lancer.cause_echec([]), "sortie vide")


if __name__ == "__main__":
    unittest.main()
