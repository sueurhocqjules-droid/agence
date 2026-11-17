import unittest

from agence import diagnostic_chaines as d, organisation


def chaine(enfants, langue, pays):
    return {"snippet": {"defaultLanguage": langue, "country": pays}, "status": {"madeForKids": enfants}}


def video(statut="public", enfants=False, region=None):
    v = {"snippet": {}, "status": {"privacyStatus": statut, "madeForKids": enfants}, "contentDetails": {}}
    if region:
        v["contentDetails"]["regionRestriction"] = region
    return v


class Diagnostic(unittest.TestCase):
    def test_les_differences_de_chaine_et_de_videos_sont_trouvees(self):
        res = d.diagnostic({"es": chaine(True, "en", None), "pt": chaine(False, "pt", "BR")},
                           {"es": [video(enfants=True, region={"blocked": ["ES"]}), video()], "pt": [video(), video()]})
        self.assertEqual(res["chaine"]["madeForKids"], (True, False))
        self.assertEqual(res["chaine"]["country"], (None, "BR"))
        self.assertIn("regionRestriction", res["videos"])
        self.assertIn("madeForKids", res["videos"])
        self.assertNotIn("privacyStatus", res["videos"])
        self.assertIn("chaine madeForKids : es=True pt=False", d.resume(res))

    def test_des_reglages_identiques_ne_donnent_aucune_difference(self):
        res = d.diagnostic({"es": chaine(False, "pt", "BR"), "pt": chaine(False, "pt", "BR")},
                           {"es": [video()], "pt": [video()]})
        self.assertEqual((res["chaine"], res["videos"]), ({}, {}))

    def test_le_script_est_declare_avec_son_proprietaire(self):
        s = organisation.scripts()["diagnostic_chaines"]
        self.assertEqual(s["module"], "agence.diagnostic_chaines")
        self.assertIn("diagnostic_chaines", organisation.fiches()[s["proprietaire"]]["scripts"])

    def test_aucune_ecriture_sur_les_chaines(self):
        source = open(d.__file__, encoding="utf-8").read()
        for interdit in (".insert(", ".update(", ".delete(", ".set("):
            self.assertNotIn(interdit, source)


if __name__ == "__main__":
    unittest.main()
