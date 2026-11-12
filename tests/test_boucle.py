"""Tests de la boucle d'amélioration (étape 7) : verdicts, mesures, retours, changements et annulations, choix fermés.

python -m unittest discover tests
"""
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agence import consignes, mesures, organisation, registre
from agents import chef_contenu, critique, direction, flux, programmateur, surete

T = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)
FICHE = """+++
id = "essai"
titre = "Poste d'essai"
superieur = "direction"
+++
# Poste d'essai

## Mission
Faire.

## Consignes
- Ancienne consigne

## Retours
(rien encore)
"""


class Dossiers(unittest.TestCase):
    """Registre et organisation dans un dossier temporaire, sans commit."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "registre").mkdir()
        (self.tmp / "organisation" / "postes").mkdir(parents=True)
        (self.tmp / "organisation" / "postes" / "essai.md").write_text(FICHE, encoding="utf-8")
        self.anciens = registre.DOSSIER, organisation.DOSSIER, consignes.RACINE
        registre.DOSSIER, organisation.DOSSIER, consignes.RACINE = self.tmp / "registre", self.tmp / "organisation", self.tmp

    def tearDown(self):
        registre.DOSSIER, organisation.DOSSIER, consignes.RACINE = self.anciens
        shutil.rmtree(self.tmp)


class Journal(Dossiers):
    def test_le_verdict_s_ajoute_sans_reecrire_la_decision(self):
        ident = registre.decider("direction", "d", "p", mesure="vues_semaine", avant=10, attendu=20, echeance="x")
        registre.juger(ident, "juste", 25, "ok")
        self.assertEqual(len((registre.DOSSIER / "decisions.jsonl").read_text(encoding="utf-8").splitlines()), 2)
        [d] = registre.decisions()
        self.assertEqual((d["id"], d["verdict"]["verdict"], d["verdict"]["valeur"]), (ident, "juste", 25))

    def test_verdict_hors_liste_refuse(self):
        with self.assertRaises(ValueError):
            registre.juger("x", "bof", 1, "")


class Verdict(unittest.TestCase):
    def d(self, avant, attendu, mesure="vues_semaine"):
        return {"mesure": mesure, "avant": avant, "attendu": attendu}

    def test_hausse_atteinte(self):
        self.assertEqual(critique.verdict(self.d(100, 150), 160)[::2], ("juste", True))

    def test_hausse_manquee_mais_dans_le_bon_sens(self):
        self.assertEqual(critique.verdict(self.d(100, 150), 120)[::2], ("fausse", True))

    def test_hausse_manquee_sans_amelioration(self):
        self.assertEqual(critique.verdict(self.d(100, 150), 90)[::2], ("fausse", False))

    def test_baisse_atteinte(self):
        self.assertEqual(critique.verdict(self.d(20, 10, "cout_claude_semaine"), 8)[::2], ("juste", True))

    def test_sans_mesure_chiffree(self):
        self.assertEqual(critique.verdict({"mesure": None, "attendu": None}, None)[0], "indeterminee")


class Mesures(unittest.TestCase):
    def stat(self, releve, vid, vues, chaine="en"):
        return {"releve": releve.isoformat(), "chaine": chaine, "video_id": vid, "vues": str(vues)}

    def test_vues_gagnees_sur_7_jours(self):
        stats = [self.stat(T - timedelta(days=8), "a", 100), self.stat(T - timedelta(days=1), "a", 150),
                 self.stat(T - timedelta(days=1), "b", 30, "es")]
        self.assertEqual(mesures.vues_gagnees(stats, T), 80)
        self.assertEqual(mesures.vues_gagnees(stats, T, "en"), 50)
        self.assertIsNone(mesures.vues_gagnees(stats, T - timedelta(days=9)))

    def test_jours_de_stock_selon_l_etat_a_la_date(self):
        ligne = lambda nom, chaine, etat, sortie, maj: {"nom": nom, "chaine": chaine, "etat": etat,
                                                        "sortie_prevue": sortie.isoformat(), "maj": maj.isoformat()}
        stock = [ligne("a-en", "en", "programme", T + timedelta(days=1), T - timedelta(days=1)),
                 ligne("b-en", "en", "programme", T + timedelta(days=2), T - timedelta(days=1)),
                 ligne("c-en", "en", "programme", T + timedelta(days=3), T + timedelta(hours=1)),  # programmée après T
                 ligne("a-es", "es", "programme", T - timedelta(hours=1), T - timedelta(days=2))]  # déjà sortie
        heures = {"en": [1, 18], "es": [2, 19], "pt": [16, 23]}
        self.assertEqual(mesures.jours_de_stock(stock, [], heures, T, "en"), 1.0)
        self.assertEqual(mesures.jours_de_stock(stock, [], heures, T), 0.0)
        # Le relevé YouTube ajoute les vidéos programmées hors de l'agence, sans compter deux fois les siennes
        releve = lambda sortie, statut="private": {"releve": (T - timedelta(hours=2)).isoformat(), "chaine": "en",
                                                   "statut": statut, "sortie": sortie.isoformat(), "video_id": "x",
                                                   "vues": "0", "titre": "t"}
        stats = [releve(T + timedelta(days=1)), releve(T + timedelta(days=4)), releve(T - timedelta(days=1), "public")]
        self.assertEqual(mesures.jours_de_stock(stock, stats, heures, T, "en"), 1.5)

    def test_mesure_inconnue_refusee(self):
        with self.assertRaises(ValueError):
            mesures.valeur("abonnes", T, {})


class Fiches(Dossiers):
    def test_quatre_retours_gardes(self):
        for i in range(6):
            consignes.ajouter_retour("essai", "direction", f"retour {i}", jour=f"2026-11-0{i + 1}")
        retours = consignes.lire_section(consignes.chemin_fiche("essai").read_text(encoding="utf-8"), "Retours")
        self.assertEqual([l[-1] for l in retours.splitlines()], ["2", "3", "4", "5"])
        self.assertNotIn("rien encore", retours)

    def test_retour_de_plus_de_trois_lignes_refuse(self):
        with self.assertRaises(ValueError):
            consignes.ajouter_retour("essai", "direction", "a\nb\nc\nd")

    def test_changement_puis_annulation(self):
        chemin = consignes.chemin_fiche("essai")
        consignes.changer("essai", "direction", "organisation/postes/essai.md", "- Nouvelle consigne", "essai",
                          "vues_semaine", 100, 150, 14, section="Consignes")
        self.assertIn("- Nouvelle consigne", chemin.read_text(encoding="utf-8"))
        with self.assertRaises(ValueError):  # un seul changement en attente par poste
            consignes.changer("essai", "direction", "organisation/postes/essai.md", "- Autre", "x",
                              "vues_semaine", 100, 150, 14, section="Consignes")
        decision = consignes.en_attente("essai")
        self.assertTrue(consignes.annuler(decision, "rien amélioré"))
        self.assertEqual(chemin.read_text(encoding="utf-8"), FICHE)

    def test_changement_sans_prediction_valable_refuse(self):
        for mesure, attendu, jours in (("abonnes", 150, 14), ("vues_semaine", 100, 14), ("vues_semaine", 150, 3)):
            with self.assertRaises(ValueError):
                consignes.changer("essai", "direction", "organisation/postes/essai.md", "- X", "x",
                                  mesure, 100, attendu, jours, section="Consignes")


class ChoixFermes(unittest.TestCase):
    heures = {"en": [1, 18], "es": [2, 19], "pt": [16, 23]}

    def test_proposition_de_creneau_valide(self):
        p = {"chaine": "en", "ancienne": 18, "nouvelle": 20, "attendu": 600}
        self.assertEqual(programmateur.valider(p, self.heures, {"en": 500}, 14), ("en", [1, 20], 600))

    def test_propositions_de_creneau_refusees(self):
        for p in ({"chaine": "fr", "ancienne": 18, "nouvelle": 20, "attendu": 600},
                  {"chaine": "en", "ancienne": 17, "nouvelle": 20, "attendu": 600},
                  {"chaine": "en", "ancienne": 18, "nouvelle": 1, "attendu": 600},
                  {"chaine": "en", "ancienne": 18, "nouvelle": 24, "attendu": 600},
                  {"chaine": "en", "ancienne": 18, "nouvelle": 20, "attendu": 400},
                  {"chaine": "en", "ancienne": 18, "nouvelle": 20, "attendu": 9000}):
            with self.assertRaises(ValueError, msg=p):
                programmateur.valider(p, self.heures, {"en": 500}, 14)

    def test_cadence_dans_le_budget(self):
        plus = {"chaine": "en", "ancienne": None, "nouvelle": 12, "attendu": 600}
        self.assertEqual(programmateur.valider(plus, self.heures, {"en": 500}, 21)[1], [1, 12, 18])
        for capacite in (20, None):   # 3 sorties par jour = 21 sujets par semaine, ou coût d'un sujet inconnu
            with self.assertRaises(ValueError):
                programmateur.valider(plus, self.heures, {"en": 500}, capacite)
        moins = {"chaine": "es", "ancienne": 2, "nouvelle": None, "attendu": 600}
        self.assertEqual(programmateur.valider(moins, self.heures, {"es": 500}, None)[1], [19])
        with self.assertRaises(ValueError):   # jamais sous une sortie par jour
            programmateur.valider(moins, {**self.heures, "es": [2]}, {"es": 500}, None)

    def test_reduction_forcee(self):
        groupes = {("en", 1): [50, 70], ("en", 18): [200]}
        heures = {"en": [1, 18], "es": [2, 19], "pt": [16]}
        self.assertEqual(programmateur.reduction_forcee(heures, groupes), {"en": [18], "es": [2], "pt": [16]})
        un = {"en": [18], "es": [2], "pt": [16]}
        self.assertEqual(programmateur.reduction_forcee(un, groupes), un)

    def test_cout_d_un_sujet_et_capacite(self):
        seance = lambda dollars, sujets: {"dollars_equiv": str(dollars), "sujets": str(sujets)}
        # anciennes lignes sans sujets ignorées, séance ratée (0 sujet) comptée : elle a coûté sans livrer
        atelier = [seance(9, ""), seance(14.2, 7), seance(3.6, 1), seance(1, 0)]
        self.assertEqual(mesures.cout_sujet(atelier), 2.35)
        self.assertIsNone(mesures.cout_sujet([seance(9, "")]))
        self.assertIsNone(mesures.cout_sujet([seance(8, 0)]))
        # fenêtre : depuis la 2e dernière séance qui a livré, la séance ratée d'avant sort du calcul
        self.assertEqual(mesures.cout_sujet([seance(50, 0), seance(4, 2), seance(2, 0), seance(4, 2)], seances=2), 2.5)
        capacite, cout, budget = mesures.capacite(atelier)
        self.assertEqual(capacite, int(budget // 2.35))

    def test_la_reserve_de_jules_sort_du_plafond(self):
        lundi = datetime(2026, 11, 9, tzinfo=timezone.utc)
        atelier = [{"debut": "2026-11-11T12:43:12Z", "agent": "auteur", "dollars_equiv": "14", "appels_gratuits": "0"},
                   {"debut": "2026-11-12T12:00:00Z", "agent": "auteur", "dollars_equiv": "28", "appels_gratuits": "0",
                    "reserve_usd": "20"}]
        c = surete.compteur(lundi + timedelta(days=4), [], atelier, {"claude": {"dollars_par_pourcent": 0}})
        self.assertEqual((c["dollars"], c["reserve"], c["hors_reserve"]), (42, 20, 22))

    def test_creneaux_du_flux_suivent_les_heures(self):
        paris = flux.PARIS
        debut = datetime(2026, 11, 16, 12, tzinfo=paris)
        prochains = flux.creneaux([20, 9], set(), debut)
        self.assertEqual([next(prochains).hour for _ in range(3)], [20, 9, 20])

    def test_besoin_de_sujets(self):
        stock = [{"nom": "a-en", "chaine": "en", "etat": "programme", "sortie_prevue": (T + timedelta(days=1)).isoformat(),
                  "maj": T.isoformat()}]
        titres = {s: {l: f"{s} {l}" for l in ("en", "es", "pt")} for s in ("a", "b", "c")}
        stats = [{"chaine": "en", "titre": "c en"}]   # c déjà en ligne en anglais (publié avant l'agence)
        attente = chef_contenu.sujets_en_attente(["a", "b", "c"], titres, stats, stock)
        self.assertEqual(attente, {"en": 1, "es": 3, "pt": 3})
        manque, detail = chef_contenu.besoin(stock, [], {"en": [1, 18]}, attente, T)
        self.assertEqual(detail["en"], {"programmees": 1, "sujets_en_attente": 1, "a_couvrir": 28})
        self.assertEqual(manque, 26)

    def test_schema_de_la_direction_limite_les_postes(self):
        s = direction.schema(["chef-contenu"])
        self.assertEqual(s["properties"]["consignes"]["items"]["properties"]["poste"]["enum"], ["chef-contenu"])
        self.assertIn(None, s["properties"]["decisions"]["items"]["properties"]["mesure"]["enum"])


if __name__ == "__main__":
    unittest.main()
