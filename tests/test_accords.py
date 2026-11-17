import unittest
from unittest import mock

from agence import accords, organisation, questions


class AccordParTelegram(unittest.TestCase):
    def test_actions_de_pr_acceptees_et_fermees(self):
        questions.verifier("accord:49")
        questions.verifier("refus:49")
        for mauvaise in ("accord:abc", "accord:", "refus:49;rm", "fusion:49"):
            with self.assertRaises(ValueError):
                questions.verifier(mauvaise)

    def test_oui_pose_l_etiquette_puis_fusionne_avec_le_jeton_de_jules(self):
        with mock.patch.dict("os.environ", {"FUSION_TOKEN": "jeton-de-jules"}), \
             mock.patch.object(accords, "_gh", return_value="") as gh:
            questions.appliquer("accord:49", "réponse oui")
        self.assertEqual([c.args[:3] for c in gh.call_args_list],
                         [("pr", "edit", "49"), ("pr", "merge", "49")])
        self.assertTrue(all(c.kwargs["jeton"] == "jeton-de-jules" for c in gh.call_args_list))

    def test_sans_jeton_la_reponse_echoue_proprement(self):
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(accords, "_gh") as gh:
            with self.assertRaises(RuntimeError):
                questions.appliquer("refus:49", "réponse non")
        gh.assert_not_called()

    def test_une_seule_question_par_pr_protegee_sans_accord(self):
        prs = [{"number": n} for n in (1, 2, 3, 4)]
        raisons = {1: ["MISSION.md"], 2: [], 3: ["reveil.yml"], 4: ["autorisations.toml"]}
        accord = {1: False, 3: True, 4: False}
        demandes = accords.a_demander(prs, {"accord:4"}, raisons.get, accord.get)
        self.assertEqual([(p["number"], r) for p, r in demandes], [(1, ["MISSION.md"])])

    def test_les_cles_passent_seulement_aux_scripts_qui_en_ont_besoin(self):
        cles = organisation.autorisations()
        self.assertEqual(cles["FUSION_TOKEN"], {"reponses"})
        self.assertIn("accords", cles["GH_TOKEN"])
        self.assertIn("accords", organisation.scripts())


if __name__ == "__main__":
    unittest.main()
