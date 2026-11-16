"""Diagnostic de la chaîne es : écarts avec pt et correction.  python -m unittest discover tests"""
import unittest

from agents import diagnostic_es as d


def video(id_, categorie="27", licence="youtube", enfants=False, visibilite="public", langue="pt"):
    return {"id": id_, "snippet": {"title": id_, "categoryId": categorie, "defaultLanguage": langue},
            "status": {"privacyStatus": visibilite, "license": licence, "selfDeclaredMadeForKids": enfants,
                       "madeForKids": enfants, "uploadStatus": "processed", "embeddable": True},
            "contentDetails": {}}


class Faux:
    """Faux client YouTube : garde les mises à jour reçues."""
    def __init__(self):
        self.mises = []

    def videos(self):
        return self

    def update(self, part, body):
        self.mises.append(body)
        return self

    def execute(self):
        return {}


def releve(brut, chaine=None):
    return {"chaine": chaine or {"pays": "BR"}, "videos": [d.reglages_video(v) for v in brut], "brut": brut, "yt": Faux()}


class Diagnostic(unittest.TestCase):
    def test_deux_chaines_identiques_sans_ecart(self):
        a, b = releve([video("a")]), releve([video("b")])
        self.assertEqual(d.ecarts(a, b), [])

    def test_ecarts_de_chaine_et_de_videos(self):
        es = releve([video("a", categorie="22", enfants=True)], {"pays": None})
        pt = releve([video("b")], {"pays": "BR"})
        champs = {(e["portee"], e["champ"]) for e in d.ecarts(es, pt)}
        self.assertIn(("chaine", "pays"), champs)
        self.assertIn(("videos", "categorie"), champs)
        self.assertIn(("videos", "declare_enfants"), champs)
        self.assertNotIn(("videos", "licence"), champs)

    def test_la_visibilite_est_signalee(self):
        es = releve([video("a", visibilite="private")])
        pt = releve([video("b")])
        self.assertIn(("videos", "visibilite"), {(e["portee"], e["champ"]) for e in d.ecarts(es, pt)})

    def test_correction_met_es_comme_pt_sans_toucher_la_visibilite(self):
        es = releve([video("a", categorie="22", enfants=True, visibilite="private")])
        pt = releve([video("b", enfants=False)])
        faits = d.corriger(es, pt)
        self.assertEqual(sorted(faits["a"]), ["categoryId", "selfDeclaredMadeForKids"])
        envoye = es["yt"].mises[0]
        self.assertEqual(envoye["snippet"]["categoryId"], "27")
        self.assertEqual(envoye["status"]["privacyStatus"], "private")
        self.assertNotIn("madeForKids", envoye["status"])
        self.assertNotIn("uploadStatus", envoye["status"])

    def test_rien_a_corriger_aucune_ecriture(self):
        es, pt = releve([video("a")]), releve([video("b")])
        self.assertEqual(d.corriger(es, pt), {})
        self.assertEqual(es["yt"].mises, [])


if __name__ == "__main__":
    unittest.main()
