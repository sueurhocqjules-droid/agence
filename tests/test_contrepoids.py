"""Tests du contrepoids, des essais et de la mémoire (étape 12, sous-étapes 9 et 18).

Le Critique juge les décisions du Responsable de l'organisation et défait seul un changement de poste qui n'a rien
amélioré ; registre/essais.jsonl tient la durée minimale d'un essai ; organisation/MEMOIRE.md est tenue par le Critique
et lue par la Direction.

python -m unittest discover tests
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from agence import consignes, essais, memoire, organisation, registre
from agents import critique, direction
from agents import responsable_organisation as ro

T = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)
CRENEAUX = "[en]\nheures = [1, 18]\n[es]\nheures = [2, 19]\n[pt]\nheures = [16, 23]\n"
PREUVE = "registre/decisions.jsonl, direction-20261101120000000000"


class Dossiers(unittest.TestCase):
    """Registre et organisation dans un dossier temporaire, sans l'atelier ni commit."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "registre").mkdir()
        (self.tmp / "organisation" / "postes").mkdir(parents=True)
        (self.tmp / "organisation" / "creneaux.toml").write_text(CRENEAUX, encoding="utf-8")
        self.anciens = registre.DOSSIER, organisation.DOSSIER, consignes.RACINE
        registre.DOSSIER, organisation.DOSSIER, consignes.RACINE = self.tmp / "registre", self.tmp / "organisation", self.tmp
        atelier = mock.patch.object(critique.surete, "couts_atelier", lambda: [])
        atelier.start()
        self.addCleanup(atelier.stop)
        self.demandes = []

    def tearDown(self):
        registre.DOSSIER, organisation.DOSSIER, consignes.RACINE = self.anciens
        shutil.rmtree(self.tmp)

    def demander(self, titre, quoi, pourquoi, par, preuve=""):
        self.demandes.append({"titre": titre, "quoi": quoi, "pourquoi": pourquoi, "par": par, "preuve": preuve})
        return 77

    def cout(self, quand, dollars):
        registre.ajouter("couts", [{"debut": quand.isoformat(), "agent": "direction", "duree_s": 1, "jetons_claude": 0,
                                    "dollars_equiv": dollars, "appels_gratuits": 0, "resultat": "ok"}])

    def changement(self, organisation_, attendu=5, auteur="responsable-organisation", echeance=None):
        """Une décision échue : le coût Claude de la semaine devait passer de 10 à `attendu` dollars."""
        return registre.decider(auteur, "changement de poste : supprimer le poste veilleur", "il ne sert pas",
                                "le coût baisse", "cout_claude_semaine", (echeance or T - timedelta(days=1)).isoformat(),
                                10, attendu, organisation=organisation_)

    def juger(self, fiches=None):
        return critique.juger_decisions(T, essai=False, annuler_un_poste=lambda d, raison: critique.annuler_poste(
            d, raison, demander=self.demander, fiches=fiches or {}))


class ContrepoidsDesPostes(Dossiers):
    SUPPRIMER = {"action": "supprimer", "postes": ["veilleur"], "nouveau": None, "superieur": "chef-recherche"}

    def test_une_suppression_qui_n_a_rien_ameliore_est_jugee_fausse_et_annulee(self):
        registre.pause("veilleur", "responsable-organisation", "poste supprimé")
        ident = self.changement(self.SUPPRIMER)
        self.cout(T - timedelta(days=3), 12)      # 12 $ mesurés : pire que les 10 $ d'avant, loin des 5 attendus
        (rendu,) = self.juger()
        self.assertEqual(rendu["verdict"], "fausse")
        self.assertIn("veilleur repris", rendu["annule"])
        self.assertIn("demande à l'Ingénierie #77", rendu["annule"])
        # le poste reprend tout de suite : la dernière ligne de sa cible fait foi
        derniere = [l for l in registre.lire("pauses") if l["cible"] == "veilleur"][-1]
        self.assertEqual((derniere["action"], derniere["par"]), ("reprise", "critique"))
        # la fiche est remise par l'Ingénierie, avec la décision en preuve
        (demande,) = self.demandes
        self.assertEqual(demande["titre"], "Remettre le poste veilleur en service")
        self.assertIn("en_service", demande["quoi"])
        self.assertIn("chef-recherche", demande["quoi"])
        self.assertIn(ident, demande["preuve"])
        decisions = registre.decisions()
        jugee = next(d for d in decisions if d["id"] == ident)
        self.assertEqual((jugee["verdict"]["verdict"], jugee["verdict"]["valeur"]), ("fausse", 12.0))
        self.assertTrue(any(d["auteur"] == "critique" and d["decision"].startswith("annulation du changement de poste")
                            for d in decisions))
        # rien à rejuger au passage suivant
        self.assertEqual(self.juger(), [])
        # la leçon entre en mémoire, avec la décision en preuve
        lignes = critique.tenir_memoire(T, [rendu], [], essai=False)
        (lecon,) = memoire.lire()
        self.assertIn("supprimer le poste veilleur", lecon["fait"])
        self.assertIn(ident, lecon["preuve"])
        self.assertIn("annulé", lignes[0])

    def test_une_suppression_qui_a_marche_reste(self):
        self.changement(self.SUPPRIMER)
        self.cout(T - timedelta(days=3), 4)
        (rendu,) = self.juger()
        self.assertEqual((rendu["verdict"], rendu["annule"]), ("juste", None))
        self.assertEqual(self.demandes, [])
        self.assertEqual(registre.lire("pauses"), [])

    def test_manquee_mais_dans_le_bon_sens_reste(self):
        self.changement(self.SUPPRIMER)
        self.cout(T - timedelta(days=3), 8)       # 8 $ : pas les 5 attendus, mais mieux que 10
        (rendu,) = self.juger()
        self.assertEqual((rendu["verdict"], rendu["annule"]), ("fausse", None))
        self.assertEqual(self.demandes, [])

    def test_une_decision_pas_encore_echue_n_est_pas_jugee(self):
        self.changement(self.SUPPRIMER, echeance=T + timedelta(days=5))
        self.cout(T - timedelta(days=3), 12)
        self.assertEqual(self.juger(), [])

    def test_en_essai_rien_n_est_ecrit(self):
        self.changement(self.SUPPRIMER)
        self.cout(T - timedelta(days=3), 12)
        (rendu,) = critique.juger_decisions(T, essai=True, annuler_un_poste=self.fail)
        self.assertEqual(rendu["verdict"], "fausse")
        self.assertIsNone(registre.decisions()[0]["verdict"])

    def test_la_direction_est_jugee_comme_les_autres(self):
        ident = registre.decider("direction", "moins de séances", "p", "le coût baisse", "cout_claude_semaine",
                                 (T - timedelta(days=1)).isoformat(), 10, 5)
        self.cout(T - timedelta(days=3), 12)
        (rendu,) = self.juger()
        self.assertEqual((rendu["id"], rendu["auteur"], rendu["verdict"], rendu["annule"]),
                         (ident, "direction", "fausse", None))   # sans changement à défaire : jugée, rien à annuler

    def test_une_fusion_annulee_est_defaite_par_l_ingenierie(self):
        d = {"id": "x", "organisation": {"action": "fusionner", "postes": ["chef-recherche", "veilleur"]}}
        fait = critique.annuler_poste(d, "rien amélioré", demander=self.demander, fiches={})
        self.assertEqual(self.demandes[0]["titre"], "Défaire la fusion de veilleur dans chef-recherche")
        self.assertEqual(fait, ["demande à l'Ingénierie #77"])
        self.assertEqual(registre.lire("pauses"), [])

    def test_une_creation_annulee_met_le_nouveau_poste_en_pause(self):
        d = {"id": "x", "organisation": {"action": "creer", "postes": [], "nouveau": "redacteur"}}
        fait = critique.annuler_poste(d, "rien amélioré", demander=self.demander, fiches={"redacteur": {}})
        (ligne,) = registre.lire("pauses")
        self.assertEqual((ligne["cible"], ligne["action"], ligne["par"]), ("redacteur", "pause", "critique"))
        self.assertEqual(self.demandes[0]["titre"], "Supprimer le poste redacteur")
        self.assertIn("redacteur en pause", fait)

    def test_une_creation_jamais_construite_n_a_rien_a_defaire(self):
        d = {"id": "x", "organisation": {"action": "creer", "postes": [], "nouveau": "redacteur"}}
        fait = critique.annuler_poste(d, "rien amélioré", demander=self.fail, fiches={})
        self.assertIn("rien à défaire", fait[0])
        self.assertEqual(registre.lire("pauses"), [])

    def test_ingenierie_injoignable_le_poste_reprend_quand_meme_et_le_blocage_remonte(self):
        def panne(*a, **k):
            raise subprocess.CalledProcessError(1, "gh", stderr="HTTP 403")
        d = {"id": "x", "organisation": self.SUPPRIMER}
        fait = critique.annuler_poste(d, "rien amélioré", demander=panne, fiches={})
        self.assertEqual(registre.lire("pauses")[-1]["action"], "reprise")
        self.assertIn("refusée", fait[-1])
        journal = (registre.DOSSIER / "journal" / "critique.jsonl").read_text(encoding="utf-8")
        self.assertIn("bloquant", journal)

    def test_le_responsable_de_l_organisation_note_de_quoi_defaire_son_changement(self):
        fiches = {"veilleur": {"superieur": "chef-recherche"}}
        c = {"action": "supprimer", "postes": ["veilleur"], "pourquoi": "p", "prediction": "q", "mesure": None,
             "attendu": None}
        ro.appliquer(c, fiches, T, demander_ing=lambda *a: 5, demander_guichet=self.fail, pause=lambda *a, **k: None)
        (d,) = registre.decisions()
        self.assertEqual(d["organisation"], {"action": "supprimer", "postes": ["veilleur"], "nouveau": None,
                                             "superieur": "chef-recherche"})


class Essais(Dossiers):
    def stat(self, releve, vues, chaine="es", vid="a"):
        return {"releve": releve.isoformat(), "chaine": chaine, "video_id": vid, "titre": "t", "statut": "public",
                "sortie": (releve - timedelta(days=4)).isoformat(), "vues": vues, "likes": 0, "commentaires": 0}

    def test_un_essai_d_exemple_est_tenu_juge_puis_cite_par_la_refonte(self):
        debut = T - timedelta(days=28)
        ident = essais.ouvrir("direction", "es", "faits chiffrés du quotidien", 28, "quatre semaines de sorties", debut)
        # pendant la durée, la chaîne garde sa ligne
        with self.assertRaisesRegex(ValueError, "garde sa ligne"):
            essais.ouvrir("direction", "es", "autre ligne", 14, "plus vite", T - timedelta(days=10))
        self.assertEqual(critique.juger_essais(T - timedelta(days=10), essai=False)[0], [])
        # au bout de la durée, pas de refonte sans le résultat du Critique
        with self.assertRaisesRegex(ValueError, "pas encore son résultat"):
            essais.ouvrir("direction", "es", "autre ligne", 14, "plus vite", T)
        registre.ajouter("stats", [self.stat(debut - timedelta(days=8), 100), self.stat(debut - timedelta(days=1), 150),
                                   self.stat(T - timedelta(days=8), 400), self.stat(T - timedelta(days=1), 420)])
        juges, lignes = critique.juger_essais(T, essai=False)
        self.assertEqual([e["id"] for e in juges], [ident])
        (e,) = essais.etat()
        self.assertEqual(e["resultat"]["chiffres"]["au_debut"], 50)
        self.assertEqual(e["resultat"]["chiffres"]["a_la_fin"], 20)
        self.assertIn("durée de 28 jours tenue", e["resultat"]["resultat"])
        self.assertIn("essai jugé", lignes[0])
        self.assertEqual(critique.juger_essais(T, essai=False)[0], [])     # jugé une seule fois
        # le résultat entre en mémoire
        critique.tenir_memoire(T, [], juges, essai=False)
        self.assertIn(ident, memoire.lire()[0]["preuve"])
        # la refonte est possible, et le script cite lui-même l'essai précédent
        nouveau = essais.ouvrir("direction", "es", "autre ligne", 14, "deux semaines suffisent", T)
        suivant = essais.etat()[-1]
        self.assertEqual((suivant["id"], suivant["precedent"]["id"]), (nouveau, ident))
        self.assertEqual(suivant["precedent"]["resultat"], e["resultat"]["resultat"])
        d = essais.dossier(T)
        self.assertEqual([x["id"] for x in d["en_cours"]], [nouveau])
        self.assertEqual((d["en_cours"][0]["jours_restants"], d["en_cours"][0]["refonte_possible"]), (14, False))
        self.assertEqual(d["chaines_sans_essai"], ["en", "pt"])
        self.assertEqual([x["id"] for x in d["passes"]], [ident])

    def test_en_essai_le_critique_n_ecrit_pas_le_resultat(self):
        essais.ouvrir("direction", "es", "ligne", 7, "une semaine", T - timedelta(days=8))
        self.assertEqual(len(critique.juger_essais(T, essai=True)[0]), 1)
        self.assertIsNone(essais.etat()[0]["resultat"])

    def test_un_essai_arrete_avant_sa_duree_est_signale(self):
        ident = essais.ouvrir("direction", "pt", "ligne", 28, "quatre semaines", T - timedelta(days=5))
        essais.arreter(ident, "direction", "changement d'avis", T - timedelta(days=1))
        juges, lignes = critique.juger_essais(T, essai=False)
        self.assertEqual(juges, [])
        self.assertIn("durée non tenue", lignes[0])
        # arrêté : la chaîne est libre, mais le nouvel essai cite quand même le précédent
        essais.ouvrir("direction", "pt", "autre", 14, "r", T)
        self.assertIn("arrêté : changement d'avis", essais.etat()[-1]["precedent"]["resultat"])
        with self.assertRaises(ValueError):
            essais.arreter(ident, "direction", "encore", T)

    def test_essais_refuses(self):
        for chaine, ligne, jours, raison in (("fr", "l", 14, "r"), ("en", "", 14, "r"), ("en", "l", 14, ""),
                                             ("en", "l", 3, "r"), ("en", "l", 400, "r"), ("en", "l", "14", "r")):
            with self.assertRaises(ValueError, msg=(chaine, ligne, jours, raison)):
                essais.ouvrir("direction", chaine, ligne, jours, raison, T)
        self.assertEqual(essais.etat(), [])


class Memoire(Dossiers):
    def test_la_vraie_memoire_est_amorcee_et_chaque_lecon_a_sa_preuve(self):
        organisation.DOSSIER = self.anciens[1]
        lecons = memoire.lire()
        self.assertGreaterEqual(len(lecons), 7)
        self.assertLessEqual(len(lecons), memoire.MAXIMUM)
        for l in lecons:
            self.assertTrue(all(l[c] for c in memoire.COLONNES), l)
            self.assertRegex(l["preuve"], memoire.PREUVE)
            datetime.fromisoformat(l["date"]), datetime.fromisoformat(l["revoir"])
        texte = " ".join(l["fait"] for l in lecons)
        for attendu in ("espagnole", "3,74 $", "5 h", "DSH", "ffmpeg", "uploadLimitExceeded", "Instagram"):
            self.assertIn(attendu, texte)
        # le fichier se relit et se réécrit à l'identique : le Critique peut le tenir sans rien perdre
        avant = memoire.chemin().read_text(encoding="utf-8")
        organisation.DOSSIER = self.tmp / "organisation"
        memoire.ecrire(lecons)
        self.assertEqual(memoire.chemin().read_text(encoding="utf-8"), avant)

    def test_ajouter_refuse_sans_preuve_en_double_ou_quand_elle_est_pleine(self):
        self.assertIsNone(memoire.ajouter("Le format long | ne marche pas", PREUVE, "ne pas le refaire", jour=T.date()))
        (l,) = memoire.lire()
        self.assertEqual((l["fait"], l["date"], l["revoir"]), ("Le format long / ne marche pas", "2026-11-15", "2027-02-13"))
        self.assertIn("preuve", memoire.ajouter("Autre fait", "on me l'a dit", "x"))
        self.assertIn("déjà", memoire.ajouter("le format long, ne marche pas", PREUVE, "x"))
        self.assertIn("manque", memoire.ajouter("Autre fait", PREUVE, ""))
        for i in range(memoire.MAXIMUM - 1):
            self.assertIsNone(memoire.ajouter(f"Fait numéro {i}", PREUVE, "x"))
        self.assertIn("pleine", memoire.ajouter("Fait de trop", PREUVE, "x"))
        self.assertEqual(len(memoire.lire()), memoire.MAXIMUM)

    def test_un_agent_propose_le_critique_integre(self):
        memoire.proposer("direction", "Publier à 3 h ne rapporte rien", PREUVE, "garder les heures du soir")
        memoire.proposer("veilleur", "Une rumeur", "vu quelque part", "tout changer")
        lignes = critique.tenir_memoire(T, [], [], essai=False)
        self.assertEqual([l["fait"] for l in memoire.lire()], ["Publier à 3 h ne rapporte rien"])
        self.assertEqual(len(lignes), 1)
        self.assertIn("leçon retenue", lignes[0])
        # le refus est dit à son auteur, et rien n'est retraité au passage suivant
        self.assertIn("preuve", (registre.DOSSIER / "journal" / "veilleur.jsonl").read_text(encoding="utf-8"))
        self.assertEqual(memoire.integrer(), [])

    def test_en_essai_les_propositions_restent_en_attente(self):
        memoire.proposer("direction", "Fait", PREUVE, "x")
        critique.tenir_memoire(T, [], [], essai=True)
        self.assertEqual(memoire.lire(), [])
        self.assertEqual(len(memoire.integrer()), 1)

    def test_lecons_a_revoir_et_retrait(self):
        memoire.ajouter("Vieille leçon", PREUVE, "x", revoir="2026-11-01", jour=T.date() - timedelta(days=60))
        memoire.ajouter("Leçon récente", PREUVE, "x", jour=T.date())
        self.assertEqual([l["fait"] for l in memoire.a_revoir(T)], ["Vieille leçon"])
        self.assertIn("date de revue", critique.tenir_memoire(T, [], [], essai=False)[0])
        self.assertTrue(memoire.retirer("vieille leçon", "critique", "ne change plus rien"))
        self.assertFalse(memoire.retirer("inconnue", "critique", "x"))
        self.assertEqual(memoire.pour_un_agent(), ["Leçon récente → x"])
        self.assertIn("leçon retirée", registre.decisions()[-1]["decision"])


class DirectionLitEtEcrit(Dossiers):
    def setUp(self):
        super().setUp()
        organisation.DOSSIER = self.anciens[1]       # les vraies fiches et la vraie mémoire, registre temporaire

    def test_le_dossier_de_la_direction_porte_la_memoire_et_les_essais(self):
        essais.ouvrir("direction", "en", "une règle absurde et ses vrais calculs", 28, "quatre semaines", T - timedelta(days=2))
        with mock.patch.object(direction.demandes, "demandes", lambda equipe: []):
            d = direction.dossier(T)
        self.assertGreaterEqual(len(d["memoire"]["lecons"]), 7)
        self.assertIn("3,74 $", json.dumps(d["memoire"], ensure_ascii=False))
        self.assertEqual(d["essais"]["en_cours"][0]["jours_restants"], 26)
        self.assertEqual(d["essais"]["chaines_sans_essai"], ["es", "pt"])

    def test_le_schema_et_la_consigne_portent_les_essais_et_les_lecons(self):
        s = direction.schema(["chef-contenu"])
        for cle in ("essais", "lecons"):
            self.assertIn(cle, s["required"])
        self.assertEqual(s["properties"]["essais"]["items"]["properties"]["chaine"]["enum"], ["en", "es", "pt", "toutes"])
        consigne = direction.consigne_systeme()
        for attendu in ("memoire :", "essais :", "- essais :", "- lecons :", "refonte_possible"):
            self.assertIn(attendu, consigne)

    def test_la_direction_ouvre_un_essai_et_propose_une_lecon(self):
        reponse = {"decisions": [], "retours": [], "consignes": [], "questions": [],
                   "essais": [{"chaine": "es", "ligne": "ligne actuelle", "duree_jours": 28, "raison": "quatre semaines"},
                              {"chaine": "es", "ligne": "déjà une autre", "duree_jours": 14, "raison": "trop tôt"}],
                   "lecons": [{"fait": "Publier à 3 h ne rapporte rien", "preuve": PREUVE, "change": "heures du soir"},
                              {"fait": "Une intuition", "preuve": "aucune", "change": "tout"}]}
        faits, refus = direction.appliquer(reponse, T, {})
        self.assertEqual(len(essais.etat()), 1)
        self.assertEqual(len(faits), 2)
        self.assertTrue(any("garde sa ligne" in r for r in refus))
        self.assertTrue(any("preuve" in r for r in refus))
        (proposee,) = registre.lire_jsonl("lecons")
        self.assertEqual(proposee["par"], "direction")
        self.assertTrue(any(d["decision"].startswith("essai ouvert sur es") for d in registre.decisions()))


class FicheDuCritique(unittest.TestCase):
    def test_le_critique_a_le_jeton_pour_demander_a_l_ingenierie(self):
        fiche = organisation.fiches()["critique"]
        self.assertIn("GH_TOKEN", fiche["env"])
        self.assertIn("critique", organisation.autorisations()["GH_TOKEN"])
        self.assertEqual(organisation.cles_accordees("critique", fiche["env"])[1], [])


if __name__ == "__main__":
    unittest.main()
