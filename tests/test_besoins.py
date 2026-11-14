"""Tests de la boucle des besoins et des voies du catalogue (étape 12, sous-étapes 2 et 10).

python -m unittest discover tests
"""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agence import besoins, catalogue, registre
from agents import analyste, chef_recherche, chercheur_outils, direction, programmateur

T = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)
POSTES = {"programmateur": {}, "auteur": {}}
LIBRE = {"date": "2026-11-14T10:00:00+00:00", "etat": "propose", "nom": "Modèle libre", "lien": "https://openrouter.ai/x/libre",
         "remplace": "auteur", "pourquoi": "écrit un sujet sans Claude", "compte_requis": False, "essai": "écrire un sujet",
         "economie_usd_semaine": 12, "besoin": "programmateur-sujets"}
COMPTE = {**LIBRE, "nom": "GPU gratuit", "lien": "https://gpu.example/offre", "compte_requis": True}
ACHAT = {"date": "2026-11-14T10:00:00+00:00", "id": "modele-payant", "poste": "auteur", "lien": "https://openrouter.ai/x/payant",
         "source_gain": "https://openrouter.ai/x/payant", "prix": 0.5, "devise": "USD", "periode": "usage",
         "poche": "claude_usd", "mesure": "cout_par_sujet", "gain_annonce": 40, "unite": "%",
         "besoin": "programmateur-sujets"}


class Registre(unittest.TestCase):
    """Registre et catalogue dans un dossier temporaire."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.anciens = registre.DOSSIER, catalogue.CATALOGUE
        registre.DOSSIER, catalogue.CATALOGUE = self.tmp, self.tmp / "catalogue.md"
        catalogue.CATALOGUE.write_text("| Ressource |\n|---|\n| `edge-tts` (https://github.com/rany2/edge-tts) |\n",
                                       encoding="utf-8")

    def tearDown(self):
        registre.DOSSIER, catalogue.CATALOGUE = self.anciens
        shutil.rmtree(self.tmp)

    def ecrire(self, nom, lignes):
        with open(self.tmp / f"{nom}.jsonl", "a", encoding="utf-8") as f:
            for l in lignes:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")

    def lignes(self, nom):
        chemin = self.tmp / f"{nom}.jsonl"
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()] if chemin.exists() else []

    def besoin(self, manque=27):
        return besoins.exprimer("programmateur", "sujets", "il manque des sujets", manque, "sujets par semaine",
                                "plus de vues", postes=POSTES)


class Exprimer(Registre):
    def test_un_besoin_chiffre_s_ecrit_au_registre(self):
        ident, ecrit = self.besoin()
        self.assertEqual((ident, ecrit), ("programmateur-sujets", True))
        (b,) = besoins.ouverts()
        self.assertEqual((b["par"], b["manque"], b["unite"], b["etat"]), ("programmateur", 27, "sujets par semaine", "ouvert"))

    def test_le_meme_besoin_ne_se_reecrit_pas_a_chaque_passage(self):
        self.besoin()
        self.assertEqual(self.besoin(), ("programmateur-sujets", False))
        self.assertEqual(len(self.lignes("besoins")), 1)

    def test_un_chiffre_qui_change_garde_la_date_du_premier_besoin(self):
        self.ecrire("besoins", [{"id": "programmateur-sujets", "date": "2026-11-10T08:00:00+00:00", "par": "programmateur",
                                 "cle": "sujets", "besoin": "b", "manque": 27, "unite": "u", "pourquoi": "p",
                                 "etat": "ouvert"}])
        self.assertTrue(self.besoin(20)[1])
        (b,) = besoins.ouverts()
        self.assertEqual((b["manque"], b["depuis"]), (20, "2026-11-10T08:00:00+00:00"))

    def test_un_manque_nul_ferme_le_besoin(self):
        self.besoin()
        self.besoin(0)
        self.assertEqual(besoins.ouverts(), [])
        self.assertEqual(self.lignes("besoins")[-1]["etat"], "clos")
        self.assertEqual(self.besoin(0), ("programmateur-sujets", False))   # rien à fermer : rien d'écrit
        self.assertEqual(len(self.lignes("besoins")), 2)

    def test_un_besoin_rouvert_repart_de_sa_nouvelle_date(self):
        self.ecrire("besoins", [
            {"id": "programmateur-sujets", "date": "2026-11-01T08:00:00+00:00", "par": "programmateur", "cle": "sujets",
             "besoin": "b", "manque": 27, "unite": "u", "pourquoi": "p", "etat": "ouvert"},
            {"id": "programmateur-sujets", "date": "2026-11-02T08:00:00+00:00", "par": "programmateur", "cle": "sujets",
             "besoin": "b", "manque": 27, "unite": "u", "pourquoi": "p", "etat": "clos"},
            {"id": "programmateur-sujets", "date": "2026-11-12T08:00:00+00:00", "par": "programmateur", "cle": "sujets",
             "besoin": "b", "manque": 5, "unite": "u", "pourquoi": "p", "etat": "ouvert"}])
        self.assertEqual(besoins.ouverts()[0]["depuis"], "2026-11-12T08:00:00+00:00")

    def test_un_besoin_sans_chiffre_ou_d_un_poste_inconnu_est_refuse(self):
        for par, manque in (("inconnu", 3), ("programmateur", "beaucoup"), ("programmateur", True)):
            with self.assertRaises(ValueError):
                besoins.exprimer(par, "sujets", "b", manque, "u", "p", postes=POSTES)
        with self.assertRaises(ValueError):
            besoins.exprimer("programmateur", "Clé invalide", "b", 3, "u", "p", postes=POSTES)
        self.assertEqual(self.lignes("besoins"), [])


class BesoinDuProgrammateur(Registre):
    def test_le_besoin_reprend_l_exemple_de_la_fiche(self):
        # 5 sorties par jour = 35 sujets par semaine, le budget en paie 8 : il manque 27 sujets par semaine
        texte, manque = programmateur.besoin_de_sujets(2, 8, 3.74, 30.0)
        self.assertEqual(manque, 27)
        self.assertIn("il manque 27 sujets par semaine", texte)
        self.assertIn("en paie 8", texte)

    def test_sans_cout_mesure_pas_de_besoin_invente(self):
        self.assertIsNone(programmateur.besoin_de_sujets(2, None, None, 30.0))
        self.assertIn("non chiffrable", programmateur.exprimer_besoin(2, None, None, 30.0))
        self.assertEqual(self.lignes("besoins"), [])

    def test_le_programmateur_ecrit_son_besoin_puis_le_ferme(self):
        self.assertIn("il manque 27", programmateur.exprimer_besoin(2, 8, 3.74, 30.0))
        self.assertIn("déjà au registre", programmateur.exprimer_besoin(2, 8, 3.74, 30.0))
        self.assertEqual(besoins.pour_la_recherche()[0]["id"], "programmateur-sujets")
        self.assertIn("comblé", programmateur.exprimer_besoin(5, 35, 0.8, 30.0))
        self.assertEqual(besoins.ouverts(), [])


class Options(Registre):
    def test_trois_options_au_plus_les_gratuites_sans_compte_d_abord(self):
        cas = {"meilleurs_cas": [{"cas": ["modele-payant"], "cout_mois": 17.3, "roi_6_mois": 0.4,
                                  "gain_eur_6_mois": [0, 1, 2], "gain_vues_6_mois": [0, 10, 20], "pessimiste_perd": True}]}
        autre = {**LIBRE, "nom": "Autre", "lien": "https://openrouter.ai/x/autre"}
        opts = besoins.options("programmateur-sujets", [COMPTE, LIBRE, autre, {**LIBRE, "besoin": None, "lien": "https://a.b/c"}],
                               [ACHAT], cas)
        self.assertEqual([o["voie"] for o in opts], ["essai", "essai", "guichet"])
        self.assertEqual(len(opts), besoins.OPTIONS_MAX)
        opts = besoins.options("programmateur-sujets", [COMPTE], [ACHAT], cas)
        self.assertEqual([(o["genre"], o["voie"]) for o in opts], [("gratuit", "guichet"), ("payant", "capital")])
        self.assertEqual(opts[1]["business_case"]["roi_6_mois"], 0.4)

    def test_un_outil_refuse_n_est_plus_une_option(self):
        self.assertEqual(besoins.options("programmateur-sujets", [LIBRE], [], exclus={LIBRE["lien"]}), [])

    def test_le_dossier_donne_l_age_et_le_delai(self):
        self.ecrire("besoins", [{"id": "programmateur-sujets", "date": "2026-11-12T08:00:00+00:00", "par": "programmateur",
                                 "cle": "sujets", "besoin": "b", "manque": 27, "unite": "sujets par semaine",
                                 "pourquoi": "p", "etat": "ouvert"}])
        self.ecrire("candidats", [LIBRE])
        (b,) = besoins.dossier(T)
        self.assertEqual((b["age_h"], b["delai_h"], b["delai_depasse"]), (82, 48, True))
        self.assertEqual([o["lien"] for o in b["options"]], [LIBRE["lien"]])
        (b,) = besoins.dossier(datetime(2026, 11, 13, 8, tzinfo=timezone.utc))
        self.assertFalse(b["delai_depasse"])

    def test_un_besoin_sans_option_le_dit(self):
        self.besoin()
        (b,) = besoins.dossier()
        self.assertEqual(b["options"], [])
        self.assertIn("aucune option", b["note"])


class Voies(Registre):
    def test_trois_voies(self):
        self.assertEqual(catalogue.voie(LIBRE), catalogue.ESSAI)
        self.assertEqual(catalogue.voie(COMPTE), catalogue.GUICHET)
        self.assertEqual(catalogue.voie(ACHAT), catalogue.CAPITAL)
        self.assertEqual(catalogue.voie({**LIBRE, "gratuit": False}), catalogue.CAPITAL)

    def test_dans_le_doute_sur_le_compte_c_est_le_guichet(self):
        for valeur in (None, "false", "non", 0, "peut-être"):
            self.assertEqual(catalogue.voie({**LIBRE, "compte_requis": valeur}), catalogue.GUICHET, valeur)
        self.assertEqual(catalogue.voie({"nom": "sans champ"}), catalogue.GUICHET)

    def test_gratuit_sans_compte_part_a_l_essai_par_l_ingenierie(self):
        appels = []
        voie, numero = catalogue.retenir(LIBRE, "la Direction", "comble le besoin de sujets",
                                         vers_ingenierie=lambda *a: appels.append(a) or 21,
                                         vers_guichet=lambda *a, **k: self.fail("pas de guichet pour un outil sans compte"))
        self.assertEqual((voie, numero), ("essai", 21))
        titre, quoi, pourquoi, par, preuve = appels[0]
        self.assertEqual((titre, par, preuve), ("Essai de l'outil Modèle libre", "la Direction", LIBRE["lien"]))
        for attendu in ("aucun secret", "ressources/catalogue.md", "tests/", LIBRE["lien"]):
            self.assertIn(attendu, quoi)
        (ligne,) = self.lignes("catalogue")
        self.assertEqual((ligne["lien"], ligne["voie"], ligne["issue"], ligne["besoin"]),
                         (LIBRE["lien"], "essai", 21, "programmateur-sujets"))

    def test_avec_compte_part_au_guichet(self):
        appels = []
        voie, numero = catalogue.retenir(COMPTE, "la Direction", "des rendus gratuits",
                                         vers_ingenierie=lambda *a: self.fail("pas d'essai avant le compte"),
                                         vers_guichet=lambda titre, **k: appels.append((titre, k)) or (14, True))
        self.assertEqual((voie, numero), ("guichet", 14))
        titre, champs = appels[0]
        self.assertEqual(titre, "Compte pour l'outil GPU gratuit")
        self.assertEqual((champs["lien"], champs["cout"], champs["par"]), (COMPTE["lien"], "0 €", "la Direction"))

    def test_un_outil_payant_n_est_jamais_retenu_ici(self):
        with self.assertRaises(ValueError):
            catalogue.retenir(ACHAT, "la Direction", "p", vers_ingenierie=self.fail, vers_guichet=self.fail)
        self.assertEqual(self.lignes("catalogue"), [])

    def test_un_outil_n_est_pas_retenu_deux_fois_ni_s_il_est_au_catalogue(self):
        catalogue.retenir(LIBRE, "la Direction", "p", vers_ingenierie=lambda *a: 21)
        with self.assertRaises(ValueError):
            catalogue.retenir(LIBRE, "la Direction", "p", vers_ingenierie=self.fail)
        with self.assertRaises(ValueError):
            catalogue.retenir({**LIBRE, "lien": "github.com/rany2/edge-tts"}, "la Direction", "p", vers_ingenierie=self.fail)

    def test_les_candidats_ouverts_excluent_refuses_retenus_inscrits_et_anciens(self):
        vieux = {**LIBRE, "lien": "https://vieux.example/x", "date": (T - timedelta(days=40)).isoformat()}
        refuse = {**LIBRE, "lien": "https://refuse.example/x"}
        inscrit = {**LIBRE, "lien": "https://github.com/rany2/edge-tts"}
        self.ecrire("candidats", [LIBRE, COMPTE, vieux, refuse, inscrit])
        self.ecrire("refus", [{"date": "2026-11-14T10:00:00+00:00", "par": "jules", "lien": "https://refuse.example/x",
                               "raison": "r"}])
        self.assertEqual({(c["lien"], c["voie"]) for c in catalogue.candidats_ouverts(T)},
                         {(LIBRE["lien"], "essai"), (COMPTE["lien"], "guichet")})
        catalogue.retenir(LIBRE, "la Direction", "p", vers_ingenierie=lambda *a: 21)
        self.assertEqual([c["lien"] for c in catalogue.candidats_ouverts(T)], [COMPTE["lien"]])


class Recherche(unittest.TestCase):
    CANDIDAT = {"nom": "Modèle libre", "lien": "https://openrouter.ai/x/libre", "remplace": "auteur", "pourquoi": "p",
                "gratuit": True, "compte_requis": False, "essai": "e"}

    def test_le_chercheur_ne_rattache_qu_a_un_besoin_ouvert(self):
        autorises = {self.CANDIDAT["lien"]}
        for besoin, attendu in (("programmateur-sujets", "programmateur-sujets"), ("invente", None), (None, None)):
            gardes, _ = chercheur_outils.valider({"candidats": [{**self.CANDIDAT, "besoin": besoin}]}, autorises,
                                                 {"auteur"}, set(), besoins_ouverts={"programmateur-sujets"})
            self.assertEqual(gardes[0]["besoin"], attendu)
        gardes, _ = chercheur_outils.valider({"candidats": [{**self.CANDIDAT, "besoin": "programmateur-sujets"}]},
                                             autorises, {"auteur"}, set())
        self.assertIsNone(gardes[0]["besoin"])

    def test_une_amelioration_payante_garde_son_besoin_ouvert(self):
        prix = [{"lien": ACHAT["lien"], "prix": 0.5, "devise": "USD", "periode": "usage"}]
        a = {k: v for k, v in ACHAT.items() if k != "date"}
        gardees, ecartees = chercheur_outils.valider_ameliorations({"ameliorations": [a]}, prix, {ACHAT["lien"]}, {"auteur"},
                                                                   set(), {"programmateur-sujets"})
        self.assertEqual((gardees[0]["besoin"], ecartees), ("programmateur-sujets", []))
        gardees, _ = chercheur_outils.valider_ameliorations({"ameliorations": [{**a, "besoin": "invente"}]}, prix,
                                                            {ACHAT["lien"]}, {"auteur"}, set(), {"programmateur-sujets"})
        self.assertNotIn("besoin", gardees[0])
        self.assertEqual(len(analyste.lire_ameliorations([ACHAT], {"auteur"})), 1)

    def test_la_consigne_du_chercheur_met_les_besoins_d_abord(self):
        texte = chercheur_outils.consigne({"besoins_ouverts": [{"id": "programmateur-sujets", "manque": 27}]}, {"auteur"})
        self.assertIn("programmateur-sujets", texte)
        self.assertLess(texte.index("D'abord les besoins"), texte.index("Choisis au plus"))

    def test_le_chef_de_la_recherche_recopie_le_besoin_du_rapport(self):
        par_lien = {LIBRE["lien"]: ("outil", LIBRE)}
        gardes, _ = chef_recherche.valider({"propositions": [{
            "source": LIBRE["lien"], "titre": "t", "proposition": "p", "preuve": "pr", "mesure": "cout_claude_semaine",
            "attendu": 20, "echeance_jours": 14, "besoin": "invente par le modèle"}]}, par_lien, {})
        self.assertEqual(gardes[0]["besoin"], "programmateur-sujets")


class Direction(Registre):
    def test_le_schema_ne_laisse_retenir_que_les_candidats_du_dossier(self):
        s = direction.schema(["chef-contenu"], outils=[LIBRE["lien"], COMPTE["lien"]])
        self.assertIn("outils", s["required"])
        self.assertEqual(s["properties"]["outils"]["items"]["properties"]["lien"]["enum"],
                         sorted([LIBRE["lien"], COMPTE["lien"]]))
        self.assertEqual(s["properties"]["outils"]["maxItems"], direction.OUTILS_MAX)
        self.assertEqual(direction.schema(["chef-contenu"])["properties"]["outils"], {"type": "array", "maxItems": 0})

    def test_la_consigne_explique_les_besoins_et_les_voies(self):
        seance = direction.consigne_systeme()
        for attendu in ("besoins :", "voie essai", "voie guichet", "voie capital", "delai_depasse", "- outils :"):
            self.assertIn(attendu, seance)

    def test_un_outil_retenu_part_sur_sa_voie_et_laisse_une_decision(self):
        self.ecrire("candidats", [LIBRE, COMPTE])
        recus = []
        faits, refus = direction.retenir_outils(
            [{"lien": LIBRE["lien"], "pourquoi": "comble le besoin"}, {"lien": "https://invente.example/x", "pourquoi": "p"}],
            T, retenir=lambda c, par, pourquoi: recus.append((c["lien"], par, pourquoi)) or ("essai", 21))
        self.assertEqual(recus, [(LIBRE["lien"], "la Direction", "comble le besoin")])
        self.assertEqual(len(faits), 1)
        self.assertIn("lien absent", refus[0])
        (d,) = registre.decisions()
        self.assertIn("essai demandé à l'Ingénierie, issue #21", d["decision"])

    def test_le_dossier_de_la_direction_porte_les_besoins_et_les_candidats(self):
        self.besoin()
        self.ecrire("candidats", [{**LIBRE, "date": (T - timedelta(days=1)).isoformat()}])
        avant = direction.demandes.demandes
        direction.demandes.demandes = lambda equipe: []
        try:
            d = direction.dossier(T)
        finally:
            direction.demandes.demandes = avant
        (b,) = d["besoins"]
        self.assertEqual((b["id"], b["manque"], b["unite"]), ("programmateur-sujets", 27, "sujets par semaine"))
        self.assertEqual([o["voie"] for o in b["options"]], ["essai"])
        self.assertEqual(direction.liens_outils(d), [LIBRE["lien"]])
        self.assertEqual(d["outils_candidats"][0]["besoin"], "programmateur-sujets")

    def test_sans_outil_retenu_rien_ne_part(self):
        self.assertEqual(direction.retenir_outils([], T, retenir=self.fail), ([], []))


if __name__ == "__main__":
    unittest.main()
