"""Veilleur, Chef de la Recherche, Chef des opérations : calculs du script et choix fermés.  python -m unittest discover tests"""
import json
import os
import tempfile
import unittest

from agents import chef_operations, chef_recherche, veilleur


def video(ident, vues, chaine="UCautre", age=20):
    return {"id": ident, "lien": f"https://www.youtube.com/shorts/{ident}", "titre": "t", "chaine": "c",
            "chaine_id": chaine, "vues": vues, "age_jours": age, "duree_s": 40}


class Veilleur(unittest.TestCase):
    def test_outliers_methode(self):
        par_chaine = {"UCautre": (1000, 12), "UCpetite": (1000, 5)}
        videos = [video("a", 5000), video("b", 2999), video("c", 9000, age=3), video("d", 9000, chaine="UCpetite"),
                  video("e", 9000, chaine=veilleur.youtube.CHAINES["en"][1]), video("f", 30000)]
        trouves = veilleur.outliers(videos, par_chaine)
        self.assertEqual([v["id"] for v in trouves], ["f", "a"])   # ratio décroissant, seuil x3 inclus
        self.assertEqual(trouves[1]["ratio"], 5.0)

    def test_duree_et_liens_de_jules(self):
        self.assertEqual(veilleur.secondes("PT1M5S"), 65)
        self.assertEqual(veilleur.secondes("PT45S"), 45)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump([{"title": "regarde youtu.be/abcdefghijk", "body": "et https://www.youtube.com/shorts/ABCDEFGHIJK "
                        "puis https://youtube.com/watch?v=abcdefghijk"}], f)
        try:
            self.assertEqual(veilleur.videos_de_jules(f.name), ["abcdefghijk", "ABCDEFGHIJK"])
        finally:
            os.unlink(f.name)
        self.assertEqual(veilleur.videos_de_jules(None), [])

    def test_choix_fermes(self):
        montres = [{**video("a", 5000), "mediane_chaine": 1000, "ratio": 5.0}]
        bon = {"lien": montres[0]["lien"], "concept": "x", "pourquoi_ca_marche": "y", "adaptation": "z",
               "effort": "nouveau type de scène", "langues": ["en", "es"], "vues": 999999999}
        gardes, _ = veilleur.valider({"fiches": [bon]}, montres, 3.74, set())
        self.assertEqual((gardes[0]["vues"], gardes[0]["cout_estime_usd"], gardes[0]["faisable"]), (5000, 7.48, True))
        cas = {"lien inventé": {**bon, "lien": "https://www.youtube.com/shorts/zzzzzzzzzzz"},
               "effort hors liste": {**bon, "effort": "facile"}, "langue inconnue": {**bon, "langues": ["fr"]},
               "sans concept": {**bon, "concept": " "}}
        for nom, f in cas.items():
            with self.subTest(nom):
                self.assertEqual([len(x) for x in veilleur.valider({"fiches": [f]}, montres, 3.74, set())], [0, 1])
        _, ecartes = veilleur.valider({"fiches": [bon]}, montres, 3.74, {bon["lien"]})
        self.assertEqual(ecartes[0]["raison"], "déjà proposé une semaine précédente")
        hors = veilleur.valider({"fiches": [{**bon, "effort": "hors de portée"}]}, montres, 3.74, set())[0][0]
        self.assertEqual((hors["faisable"], hors["cout_estime_usd"]), (False, None))


class ChefRecherche(unittest.TestCase):
    SOURCES = {"https://youtube.com/shorts/a": ("concept", {"ratio": 5.0, "vues": 5000, "titre": "t"}),
               "https://github.com/a/b": ("outil", {"nom": "B", "economie_usd_semaine": 4})}
    BON = {"source": "https://github.com/a/b", "titre": "t", "proposition": "adopter B", "preuve": "4 $ par semaine",
           "mesure": "cout_claude_semaine", "attendu": 20, "echeance_jours": 14}

    def test_preuves_recopiees_par_le_script(self):
        gardes, _ = chef_recherche.valider({"propositions": [self.BON]}, self.SOURCES, {"cout_claude_semaine": 24.0})
        self.assertEqual(gardes[0]["preuves_chiffrees"], {"nom": "B", "economie_usd_semaine": 4})
        self.assertEqual((gardes[0]["type"], gardes[0]["avant"]), ("outil", 24.0))

    def test_choix_fermes(self):
        cas = {"source inventée": {**self.BON, "source": "https://x.y/z"}, "mesure inconnue": {**self.BON, "mesure": "joie"},
               "attendu en texte": {**self.BON, "attendu": "plus"}, "attendu booléen": {**self.BON, "attendu": True},
               "échéance trop longue": {**self.BON, "echeance_jours": 60}, "sans preuve": {**self.BON, "preuve": ""}}
        for nom, p in cas.items():
            with self.subTest(nom):
                self.assertEqual([len(x) for x in chef_recherche.valider({"propositions": [p]}, self.SOURCES, {})], [0, 1])
        gardes, ecartes = chef_recherche.valider({"propositions": [self.BON] * 5}, self.SOURCES, {})
        self.assertEqual((len(gardes), len(ecartes)), (1, 2))   # 3 lues au plus, une source une fois
        self.assertEqual(chef_recherche.valider({}, self.SOURCES, {}), ([], []))

    def test_notre_mediane(self):
        stats = [{"releve": r, "chaine": "en", "statut": s, "vues": v}
                 for r, s, v in (("1", "public", "10"), ("2", "public", "100"), ("2", "public", "300"), ("2", "private", "0"))]
        self.assertEqual(chef_recherche.notre_mediane(stats), {"en": 200})


class ChefOperations(unittest.TestCase):
    def test_reveils_reussis_et_pannes_sans_trace(self):
        runs = [{"workflowName": "Réveil", "conclusion": "success", "createdAt": "2026-11-10T05:17:00Z", "url": "u1"},
                {"workflowName": "Réveil", "conclusion": "failure", "createdAt": "2026-11-10T11:17:00Z", "url": "u2"},
                {"workflowName": "Réveil", "conclusion": "failure", "createdAt": "2026-11-10T17:17:00Z", "url": "u3"},
                {"workflowName": "Semaine", "conclusion": "cancelled", "createdAt": "2026-11-09T17:37:00Z", "url": "u4"}]
        entrees = [{"agent": "flux", "date": "2026-11-10T11:30:00+00:00", "resultat": "echec"},
                   {"agent": "stats", "date": "2026-11-10T05:20:00+00:00", "resultat": "ok"},
                   {"agent": "flux", "date": "2026-11-10T05:21:00+00:00", "resultat": "refuse"}]
        c = chef_operations.chiffres(runs, entrees)
        self.assertEqual((c["reveils_reussis_pourcent"], c["reveils_par_workflow"]), (33, {"Réveil": "1/3"}))
        self.assertEqual([p["lien"] for p in c["pannes_sans_trace"]], ["u3"])   # u2 a laissé une trace au journal
        self.assertEqual(c["agents"]["flux"], {"ok": 0, "echec": 1, "refuse": 1})
        self.assertIsNone(chef_operations.chiffres([], [])["reveils_reussis_pourcent"])

    def test_choix_fermes(self):
        reponse = {"ligne": "tout va — bien", "retours": [{"poste": "maintenance", "texte": "ok"},
                                                          {"poste": "maintenance", "texte": "encore"},
                                                          {"poste": "direction", "texte": "non"}],
                   "reparations": [{"quoi": "q", "pourquoi": "p"}] * 5 + [{"quoi": ""}]}
        ligne, retours, reparations, ecartes = chef_operations.valider(reponse, ["maintenance", "expert-modeles"])
        self.assertEqual((ligne, len(retours), len(reparations), len(ecartes)), ("tout va, bien", 1, 3, 2))


if __name__ == "__main__":
    unittest.main()
