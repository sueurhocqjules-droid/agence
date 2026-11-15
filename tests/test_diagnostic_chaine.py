"""Tests du diagnostic de la chaîne es contre pt, sans appel réseau.  python -m unittest discover tests"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import diagnostic_chaine as d
from agence import lancer, registre


class Faux:
    """Un faux client YouTube : une chaîne, ses vidéos, et la trace de ce qu'on modifie."""

    def __init__(self, ident, enfants=False, videos=(), refuse=False):
        self.ident, self.enfants, self.refuse = ident, enfants, refuse
        self.videos_ = {v["id"]: v for v in videos}
        self.ordre = [v["id"] for v in videos]
        self.mises_a_jour = []

    def reponse(self, valeur):
        return mock.Mock(execute=lambda: valeur)

    def channels(self):
        faux = self

        class C:
            def list(self, part, mine):
                if part == "contentDetails":
                    return faux.reponse({"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "U"}}}]})
                return faux.reponse({"items": [{"id": faux.ident, "status": {
                    "madeForKids": faux.enfants, "selfDeclaredMadeForKids": faux.enfants, "longUploadsStatus": "allowed"},
                    "brandingSettings": {"channel": {"country": "ES" if faux.ident == "ces" else "BR"}}}]})

            def update(self, part, body):
                faux.mises_a_jour.append(("chaine", body))
                if faux.refuse:
                    raise RuntimeError("403 insufficientPermissions")
                faux.enfants = body["status"]["selfDeclaredMadeForKids"]
                return faux.reponse({})
        return C()

    def playlistItems(self):
        faux = self
        return type("P", (), {"list": lambda s, **k: faux.reponse(
            {"items": [{"contentDetails": {"videoId": i}} for i in faux.ordre]})})()

    def videos(self):
        faux = self

        class V:
            def list(self, part, id):
                return faux.reponse({"items": [faux.videos_[i] for i in id.split(",")]})

            def update(self, part, body):
                faux.mises_a_jour.append(("video", body))
                if faux.refuse:
                    raise RuntimeError("403 insufficientPermissions")
                faux.videos_[body["id"]]["status"].update(body["status"])
                if "selfDeclaredMadeForKids" in body["status"]:
                    faux.videos_[body["id"]]["status"]["madeForKids"] = body["status"]["selfDeclaredMadeForKids"]
                return faux.reponse({})
        return V()


def video(ident, prive=False, enfants=False, programmee=None, langue="es", categorie="27"):
    statut = {"privacyStatus": "private" if prive else "public", "madeForKids": enfants,
              "selfDeclaredMadeForKids": enfants, "license": "youtube", "embeddable": True}
    if programmee:
        statut["publishAt"] = programmee
    return {"id": ident, "snippet": {"defaultLanguage": langue, "categoryId": categorie}, "status": statut,
            "contentDetails": {}}


class Diagnostic(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        racine = Path(self.tmp.name)
        (racine / "journal").mkdir()
        for cible, valeur in ((registre, "DOSSIER"), (d.registre, "DOSSIER"), (d, "FICHIER")):
            patch = mock.patch.object(cible, valeur, racine if valeur == "DOSSIER" else racine / "diag.json")
            patch.start()
            self.addCleanup(patch.stop)
        self.racine = racine

    def lancer(self, es, pt):
        return d.diagnostiquer({"es": es, "pt": pt})

    def journal(self):
        chemin = self.racine / "journal" / "chef-contenu.jsonl"
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()] if chemin.exists() else []

    def decisions(self):
        return registre.lire_jsonl("decisions")

    def test_enfants_et_prive_sont_corriges_et_audites(self):
        es = Faux("ces", enfants=True, videos=[video("e1", prive=True, enfants=True), video("e2")])
        pt = Faux("cpt", videos=[video("p1", langue="pt"), video("p2", langue="pt")])
        res = self.lancer(es, pt)
        self.assertEqual(len(res["corrections"]), 2)
        self.assertEqual(es.videos_["e1"]["status"]["privacyStatus"], "public")
        self.assertFalse(es.videos_["e1"]["status"]["selfDeclaredMadeForKids"])
        self.assertFalse(es.enfants)
        self.assertEqual(len(self.decisions()), 2)
        self.assertEqual(res["differences"], [x for x in res["differences"] if d.explique(x)])
        self.assertEqual(self.journal(), [])   # plus rien d'inexpliqué
        self.assertTrue((self.racine / "diag.json").exists())

    def test_une_video_programmee_n_est_pas_rendue_publique(self):
        es = Faux("ces", videos=[video("e1", prive=True, programmee="2026-11-20T10:00:00Z")])
        pt = Faux("cpt", videos=[video("p1", langue="pt")])
        self.lancer(es, pt)
        self.assertEqual(es.mises_a_jour, [])

    def test_le_reste_n_est_pas_corrige_et_devient_un_bloquant(self):
        es = Faux("ces", videos=[video("e1", categorie="1")])
        pt = Faux("cpt", videos=[video("p1", langue="pt", categorie="27")])
        res = self.lancer(es, pt)
        self.assertEqual(es.mises_a_jour, [])
        self.assertEqual(self.decisions(), [])
        self.assertIn("categoryId", [x["champ"] for x in res["differences"]])
        bloquant = self.journal()[0]
        self.assertIn("categoryId", bloquant["bloquant"])

    def test_rien_trouve_est_un_bloquant(self):
        es, pt = Faux("ces", videos=[video("e1")]), Faux("cpt", videos=[video("p1", langue="pt")])
        self.lancer(es, pt)
        self.assertIn("aucun des champs", self.journal()[0]["bloquant"])

    def test_correction_refusee_devient_un_bloquant(self):
        es = Faux("ces", enfants=True, refuse=True, videos=[])
        pt = Faux("cpt", videos=[])
        res = self.lancer(es, pt)
        self.assertEqual(res["corrections"], [])
        self.assertEqual(self.decisions(), [])
        self.assertIn("403", self.journal()[0]["bloquant"])

    def test_meme_diagnostic_pas_de_second_bloquant(self):
        es = Faux("ces", videos=[video("e1", categorie="1")])
        pt = Faux("cpt", videos=[video("p1", langue="pt", categorie="27")])
        self.lancer(es, pt)
        self.lancer(es, pt)
        self.assertEqual(len(self.journal()), 1)


class Branchement(unittest.TestCase):
    def test_la_fiche_du_proprietaire_cite_le_script_et_le_flux_le_lance(self):
        racine = Path(__file__).resolve().parent.parent
        fiche = (racine / "organisation" / "postes" / "chef-contenu.md").read_text(encoding="utf-8")
        self.assertIn("diagnostic_chaine", fiche)
        self.assertIn("diagnostic_chaine.main()", (racine / "agents" / "flux.py").read_text(encoding="utf-8"))
        self.assertIn("propriétaire : chef-contenu", (racine / "agence" / "diagnostic_chaine.py").read_text(encoding="utf-8"))
        self.assertTrue(callable(lancer.noter_journal))


if __name__ == "__main__":
    unittest.main()
