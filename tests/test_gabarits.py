"""Gabarits Remotion : schéma, modèle gratuit simulé, et rendu d'un exemple de chaque gabarit.  python -m unittest discover tests"""
import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import gabarits, postes

REMOTION_PRET = (gabarits.REMOTION / "node_modules" / "remotion").exists() and shutil.which("npx") is not None
EDGE_TTS_PRET = shutil.which("edge-tts") is not None


def exemple(gabarit):
    return json.loads((gabarits.EXEMPLES / gabarits.GABARITS[gabarit][1]).read_text(encoding="utf-8"))


class Schema(unittest.TestCase):
    def test_les_exemples_sont_valides(self):
        for g in gabarits.GABARITS:
            self.assertEqual(gabarits.valider(g, exemple(g)), [], g)

    def test_refus_scale_zoom(self):
        d = exemple("scale-zoom")
        for abime in (lambda x: x["objets"][0].update(taille_m=-1), lambda x: x["objets"][0].update(couleur="rouge"),
                      lambda x: x["objets"].__delitem__(slice(1, None)), lambda x: x.update(voix="mot " * 200),
                      lambda x: x["objets"][1].update(taille_m=x["objets"][0]["taille_m"]), lambda x: x.pop("titre")):
            copie = copy.deepcopy(d)
            abime(copie)
            self.assertTrue(gabarits.valider("scale-zoom", copie))

    def test_refus_une_seconde_une_heure(self):
        d = exemple("one-sec-vs-one-hour")
        for abime in (lambda x: x["etats"][1].update(instant=2), lambda x: x["etats"][0].update(instant=0.2),
                      lambda x: x["etats"][2].pop("heure"), lambda x: x["etats"].pop(),
                      lambda x: x["etats"][0].update(couleur="#12")):
            copie = copy.deepcopy(d)
            abime(copie)
            self.assertTrue(gabarits.valider("one-sec-vs-one-hour", copie))
        self.assertTrue(gabarits.valider("one-sec-vs-one-hour", []))
        self.assertTrue(gabarits.valider("inconnu", {}))


class ModeleGratuit(unittest.TestCase):
    def test_le_poste_n_utilise_aucun_modele_claude(self):
        self.assertTrue(postes.POSTES["gabarits"])
        self.assertFalse([m for _, m, _ in postes.POSTES["gabarits"] if "claude" in m.lower()])

    def test_json_valide_dans_un_bloc_de_code(self):
        reponses = ["```json\n" + json.dumps(exemple("scale-zoom")) + "\n```"]
        demander = mock.Mock(side_effect=lambda *a, **k: (reponses.pop(0), "m", 1, 1, 0.1))
        self.assertEqual(gabarits.donnees_du_sujet("scale-zoom", "les animaux", demander)["titre"], exemple("scale-zoom")["titre"])
        self.assertEqual(demander.call_args[0][0], "gabarits")

    def test_un_second_essai_puis_refus(self):
        demander = mock.Mock(return_value=('{"titre": "x"}', "m", 1, 1, 0.1))
        with self.assertRaises(ValueError):
            gabarits.donnees_du_sujet("one-sec-vs-one-hour", "le sommeil", demander)
        self.assertEqual(demander.call_count, 2)
        self.assertIn("refusée", demander.call_args[0][1])

    def test_aucun_appel_au_reseau_sans_modele_simule(self):
        with mock.patch.object(gabarits.postes, "demander", side_effect=RuntimeError("réseau")):
            with self.assertRaises(RuntimeError):
                gabarits.donnees_du_sujet("scale-zoom", "x")


class Commandes(unittest.TestCase):
    def test_rendre_refuse_des_donnees_fausses_avant_toute_commande(self):
        with mock.patch.object(gabarits.subprocess, "run") as run:
            with self.assertRaises(ValueError):
                gabarits.rendre("scale-zoom", {"titre": "x"}, "x.mp4")
        run.assert_not_called()

    def test_rendre_appelle_edge_tts_puis_remotion(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(gabarits.subprocess, "run") as run:
            gabarits.rendre("scale-zoom", exemple("scale-zoom"), Path(tmp) / "a.mp4")
        commandes = [c.args[0] for c in run.call_args_list]
        self.assertIn("edge_tts", commandes[0])
        self.assertIn("render", commandes[1])
        self.assertIn("ScaleZoom", commandes[1])


class GuessTheProduct(unittest.TestCase):
    def test_refus(self):
        d = exemple("guess-the-product")
        for abime in (lambda x: x["indices"].pop(), lambda x: x["indices"].append(dict(x["indices"][0])),
                      lambda x: x["indices"][0].update(texte="Looks like an air fryer"),
                      lambda x: x["indices"][1].pop("icone"), lambda x: x.pop("produit"),
                      lambda x: x.pop("categorie"), lambda x: x.update(voix="word " * 200)):
            copie = copy.deepcopy(d)
            abime(copie)
            self.assertTrue(gabarits.valider("guess-the-product", copie))
        self.assertTrue(gabarits.valider("guess-the-product", []))

    def test_la_consigne_demande_de_l_anglais_et_trois_indices(self):
        texte = gabarits.consigne("guess-the-product", "cuisine")
        self.assertIn("anglais", texte)
        self.assertIn("3 indices", texte)

    def test_donnees_par_un_modele_gratuit(self):
        demander = mock.Mock(return_value=(json.dumps(exemple("guess-the-product")), "m", 1, 1, 0.0))
        donnees = gabarits.donnees_du_sujet("guess-the-product", "cuisine", demander)
        self.assertEqual(donnees["produit"], "Air fryer")
        self.assertEqual(demander.call_args[0][0], "gabarits")

    def test_voix_anglaise_par_defaut(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(gabarits.subprocess, "run") as run:
            gabarits.rendre("guess-the-product", exemple("guess-the-product"), Path(tmp) / "a.mp4")
        commandes = [c.args[0] for c in run.call_args_list]
        self.assertIn("en-US-AriaNeural", commandes[0])
        self.assertIn("GuessTheProduct", commandes[1])

    def test_la_duree_de_la_composition_suit_la_chronologie(self):
        source = (gabarits.REMOTION / "src" / "GuessTheProduct.tsx").read_text(encoding="utf-8")
        self.assertIn("SECONDES_PAR_INDICE = 5", source)


@unittest.skipUnless(REMOTION_PRET, "Remotion non installé (npm install dans remotion/)")
class RenduReel(unittest.TestCase):
    def test_rendu_de_chaque_gabarit_sans_voix(self):
        for g in gabarits.GABARITS:
            with tempfile.TemporaryDirectory() as tmp:
                sortie = gabarits.rendre(g, exemple(g), Path(tmp) / f"{g}.mp4", avec_voix=False)
                self.assertGreater(sortie.stat().st_size, 10000, g)

    @unittest.skipUnless(EDGE_TTS_PRET, "edge-tts non installé")
    def test_rendu_avec_voix(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(gabarits.rendre("scale-zoom", exemple("scale-zoom"), Path(tmp) / "a.mp4").exists())


if __name__ == "__main__":
    unittest.main()
