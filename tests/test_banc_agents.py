"""Banc des agents : cas bien formés, cas sans modèle rejoués, verdicts du moteur, juge en réponse fermée.

python -m unittest discover tests
"""
import unittest
from unittest import mock

from agence import banc_agents, postes, registre
from agents import chef_recherche, chercheur_outils

TEMOIN = {"id": "t", "poste": "direction", "panne": "x" * 40, "attendu": "echec", "sortie": {"seance": "texte"},
          "criteres": [{"id": "j", "type": "juge", "sur": "seance", "question": "q ?", "attendu": "non"}]}


class Cas(unittest.TestCase):
    def test_chaque_cas_est_bien_forme(self):
        cas = banc_agents.charger()
        self.assertGreaterEqual(len(cas), 11)
        for c in cas:
            with self.subTest(c["fichier"]):
                self.assertEqual(banc_agents.defauts(c), [])

    def test_chaque_panne_a_un_temoin_qui_doit_echouer_et_un_cas_qui_doit_passer(self):
        attendus = {}
        for c in banc_agents.charger():
            attendus.setdefault(c["poste"], set()).add(c.get("attendu", "passe"))
        for poste in ("chef-operations", "chercheur-outils", "direction"):
            self.assertEqual(attendus[poste], {"passe", "echec"}, poste)

    def test_les_cas_sans_modele_rendent_le_verdict_attendu(self):
        joues = 0
        for c in banc_agents.charger():
            if not banc_agents.demande_un_modele(c):
                with self.subTest(c["id"]):
                    verdict, details = banc_agents.passer(c, direct=False)
                    self.assertEqual(verdict, c.get("attendu", "passe"), details)
                    joues += 1
        self.assertGreaterEqual(joues, 5)

    def test_un_cas_mal_forme_est_dit(self):
        mauvais = {"fichier": "a.json", "id": "b", "poste": "inconnu", "panne": "court", "sortie": {}, "adaptateur": "direction",
                   "criteres": [{"id": "c", "type": "code", "verif": "rien"}, {"id": "j", "type": "juge", "attendu": "peut-être"}]}
        self.assertEqual(len(banc_agents.defauts(mauvais)), 7)


class Moteur(unittest.TestCase):
    def passer(self, avis, cas=TEMOIN):
        return banc_agents.passer(cas, juge=lambda question, texte, eviter: (avis, "juge de test"))[0]

    def test_verdicts_du_juge(self):
        self.assertEqual(self.passer("non"), "passe")
        self.assertEqual(self.passer("oui"), "echec")
        self.assertEqual(self.passer("inconnu"), "inconnu")   # dans le doute, le cas ne passe pas

    def test_le_code_tranche_avant_le_juge(self):
        cas = {**TEMOIN, "criteres": [*TEMOIN["criteres"], {"id": "c", "type": "code", "verif": "sans", "sur": "seance",
                                                             "motifs": ["texte"]}]}
        juge = mock.Mock(return_value=("non", ""))
        verdict, details = banc_agents.passer(cas, juge=juge)
        self.assertEqual(verdict, "echec")
        juge.assert_not_called()
        self.assertIn("non jugé", details[-1])

    def test_sortie_illisible_ou_agent_plante_est_un_echec(self):
        cas = {**TEMOIN, "criteres": [{"id": "c", "type": "code", "verif": "vide", "sur": "absent.0"}]}
        self.assertEqual(banc_agents.passer(cas)[0], "echec")
        plante = {"id": "p", "adaptateur": "chef-operations", "entree": {}, "criteres": []}
        self.assertEqual(banc_agents.passer(plante, direct=False)[0], "echec")

    def test_modele_muet_vaut_inconnu(self):
        cas = next(c for c in banc_agents.charger() if c["id"] == "chef-operations-semaine-calme-direct")
        with mock.patch.object(postes, "demander", side_effect=RuntimeError("aucun modèle")):
            self.assertEqual(banc_agents.passer(cas)[0], "inconnu")

    def test_sans_modele_un_cas_en_direct_est_refuse(self):
        cas = next(c for c in banc_agents.charger() if c["id"] == "chef-operations-semaine-calme-direct")
        with self.assertRaises(banc_agents.SansModele):
            banc_agents.passer(cas, direct=False)


class Juge(unittest.TestCase):
    def juger(self, *reponses):
        appels = mock.Mock(side_effect=[(r, "modele-juge", 0, 0, 0) for r in reponses])
        with mock.patch.object(postes, "demander", appels):
            return banc_agents.juger("q ?", "texte", eviter="modele-agent")[0], appels

    def test_reponse_fermee(self):
        verdict, appels = self.juger('```json\n{"verdict": "oui", "citation": "texte"}\n```')
        self.assertEqual(verdict, "oui")
        self.assertEqual(appels.call_args.args[0], "juge-banc")
        self.assertEqual(appels.call_args.kwargs, {"temperature": 0, "eviter": "modele-agent"})

    def test_hors_format_ou_inconnu_puis_second_essai(self):
        self.assertEqual(self.juger("je pense que oui", '{"verdict": "non"}')[0], "non")
        self.assertEqual(self.juger('{"verdict": "peut-être"}', '{"verdict": "inconnu"}')[0], "inconnu")

    def test_juge_injoignable(self):
        with mock.patch.object(postes, "demander", side_effect=RuntimeError("aucun modèle")):
            self.assertEqual(banc_agents.juger("q ?", "texte")[0], "inconnu")

    def test_le_juge_n_est_pas_claude_et_evite_le_modele_juge(self):
        self.assertFalse([m for _, m, _ in postes.POSTES["juge-banc"] if "claude" in m.lower()])
        vus = []
        with mock.patch.object(postes, "POSTES", {"p": [("f", "a", 1), ("f", "b", 1)]}), \
                mock.patch.object(postes, "appeler", lambda f, m, c, p, **k: (vus.append((m, k)), ("ok", 0, 0, 0))[1]):
            self.assertEqual(postes.demander("p", "c", temperature=0, eviter="a")[1], "b")
        self.assertEqual(vus, [("b", {"temperature": 0})])


class Refus(unittest.TestCase):
    """Un lien refusé (registre/refus.jsonl) ne revient ni chez le Chercheur d'outils ni chez le Chef de la Recherche."""
    LIEN = "https://github.com/x/relais"

    def test_le_relais_dsh_est_au_registre_des_refus(self):
        self.assertIn("https://github.com/Ebony-Vinyl/dsh-our-free-model", registre.refuses())

    def test_chercheur_outils(self):
        candidat = {"nom": "relais", "lien": self.LIEN, "remplace": "auteur", "gratuit": True, "pourquoi": "p", "essai": "e"}
        gardes, _ = chercheur_outils.valider({"candidats": [candidat]}, {self.LIEN}, {"auteur"}, set())
        self.assertEqual(len(gardes), 1)
        gardes, ecartes = chercheur_outils.valider({"candidats": [candidat]}, {self.LIEN}, {"auteur"}, set(), {self.LIEN + "/"})
        self.assertEqual((gardes, ecartes[0]["raison"]), ([], "déjà refusé (registre/refus.jsonl)"))

    def test_chef_recherche(self):
        outils = [{"lien": self.LIEN, "etat": "propose"}, {"lien": "https://github.com/x/sain", "etat": "propose"},
                  {"lien": "https://github.com/x/vieux", "etat": "essaye"}]
        self.assertEqual(list(chef_recherche.indexer([], outils, {self.LIEN})), ["https://github.com/x/sain"])
        self.assertEqual(len(chef_recherche.indexer([{"lien": "c", "etat": "propose"}], outils)), 3)


if __name__ == "__main__":
    unittest.main()
