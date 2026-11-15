"""Tests du Stratège (étape 12) : ce que la mission promet et que l'agence ne fait pas.

python -m unittest discover tests
"""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from agence import registre, suivi_ecarts
from agents import bilan, direction, stratege
from agents import responsable_organisation as ro

T = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
FICHES = {"direction": {"titre": "Direction"}, "critique": {"titre": "Critique"}}
CLES = {"GROQ_API_KEY", "GH_TOKEN"}


def ecart(**k):
    return {"source": "mission, règle 10", "promesse": "chaque réseau a ses stats", "constat": "3 réseaux sans stats",
            "preuve": "reseaux.reseaux_sans_stats", "objectif": 1, "voie": "direction",
            "remede": "brancher les stats", "poste": None, "besoin": None, "mesure": None, "attendu": None,
            "echeance_jours": 21} | k


def diffusion(reseau, etat="publie", date="2026-11-13T11:42:00+00:00"):
    return {"date": date, "reseau": reseau, "chaine": "en", "nom": "x", "etat": etat, "media_id": "", "note": ""}


def stat(reseau=None, releve="2026-11-15T06:00:00+00:00"):
    l = {"releve": releve, "chaine": "en", "video_id": "v1", "titre": "t", "statut": "public",
         "sortie": "2026-11-10T15:00:00+00:00", "vues": "10", "likes": "0", "commentaires": "0"}
    return l | ({"reseau": reseau} if reseau else {})


class Registre(unittest.TestCase):
    """Registre dans un dossier temporaire."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ancien = registre.DOSSIER
        registre.DOSSIER = self.tmp

    def tearDown(self):
        registre.DOSSIER = self.ancien
        shutil.rmtree(self.tmp)

    def jsonl(self, nom, lignes):
        (self.tmp / f"{nom}.jsonl").write_text("".join(json.dumps(l, ensure_ascii=False) + "\n" for l in lignes),
                                               encoding="utf-8")


class Reseaux(Registre):
    def test_reseau_qui_diffuse_sans_stats(self):
        r = stratege.reseaux(T, [diffusion("instagram"), diffusion("tiktok", "erreur")], [stat()])
        self.assertEqual(r["reseaux_sans_stats"], ["instagram"])   # TikTok n'a rien publié : pas d'angle mort
        self.assertEqual(r["par_reseau"]["youtube"]["publiees_28j"], 1)
        self.assertEqual(r["par_reseau"]["tiktok"]["autres_etats_28j"], {"erreur": 1})

    def test_diffusion_trop_ancienne_ignoree(self):
        r = stratege.reseaux(T, [diffusion("facebook", date="2026-10-01T00:00:00+00:00")], [stat()])
        self.assertEqual(r["reseaux_sans_stats"], [])

    def test_colonne_reseau_dans_stats_compte(self):
        r = stratege.reseaux(T, [diffusion("instagram")], [stat(), stat("instagram")])
        self.assertEqual(r["reseaux_sans_stats"], [])

    def test_releve_ancien_ne_compte_pas(self):
        self.assertEqual(stratege.reseaux_mesures(T - stratege.FENETRE, [stat(releve="2026-09-01T00:00:00+00:00")]),
                         set())


class Valider(unittest.TestCase):
    def valider(self, *ecarts, suivi=(), ids=()):
        return stratege.valider({"ligne": "l", "ecarts": list(ecarts), "suivi": list(suivi)}, FICHES, CLES, set(ids), T)

    def test_ecart_retenu_avec_identifiant(self):
        _, retenus, _, refus = self.valider(ecart(remede="voir @quelqu'un"))
        self.assertEqual(refus, [])
        self.assertEqual(retenus[0]["id"], "ecart-20261115-1")
        self.assertNotIn("@", retenus[0]["remede"])

    def test_voie_hors_liste_refusee(self):
        _, retenus, _, refus = self.valider(ecart(voie="jules"))
        self.assertEqual(retenus, [])
        self.assertIn("voie hors liste", refus[0])

    def test_preuve_manquante_refusee(self):
        self.assertEqual(self.valider(ecart(preuve=""))[1], [])

    def test_poste_aux_regles_du_responsable_de_l_organisation(self):
        poste = {"id": "repondeur", "titre": "Répondeur", "superieur": "direction", "mission": "répondre",
                 "moteur": "Groq", "cles": ["GROQ_API_KEY"]}
        self.assertEqual(len(self.valider(ecart(voie="poste", poste=poste))[1]), 1)
        for mauvais in ({"cles": ["STRIPE_KEY"]}, {"superieur": "inconnu"}, {"id": "direction"}):
            _, retenus, _, refus = self.valider(ecart(voie="poste", poste=poste | mauvais))
            self.assertEqual(retenus, [], mauvais)
            self.assertTrue(refus)

    def test_poste_hors_voie_poste_ignore(self):
        _, retenus, _, _ = self.valider(ecart(poste={"id": "x"}))
        self.assertIsNone(retenus[0]["poste"])

    def test_besoin_sans_nombre_refuse(self):
        for besoin in ({"cle": "stats-reseaux", "unite": "réseau"}, {"cle": "s", "manque": True, "unite": "r"},
                       {"cle": "s", "manque": 0, "unite": "r"}, {"cle": "s", "manque": 2, "unite": ""}):
            self.assertEqual(self.valider(ecart(voie="besoin", besoin=besoin))[1], [], besoin)

    def test_mesure_hors_liste_ignoree(self):
        _, retenus, _, _ = self.valider(ecart(mesure="bonheur", attendu=3))
        self.assertIsNone(retenus[0]["mesure"])
        self.assertIsNone(retenus[0]["attendu"])

    def test_pas_de_quota_seulement_un_plafond_anti_emballement(self):
        self.assertEqual(len(self.valider(*[ecart()] * 6)[1]), 6)
        self.assertEqual(len(self.valider(*[ecart()] * 30)[1]), stratege.ECARTS_MAX)

    def test_suivi_d_un_ecart_inconnu_refuse(self):
        _, _, suivi, refus = self.valider(suivi=[{"id": "ecart-1", "etat": "comble", "pourquoi": "fait"},
                                                 {"id": "ecart-2", "etat": "comble"},
                                                 {"id": "ecart-1", "etat": "oublie"}], ids={"ecart-1"})
        self.assertEqual([s["id"] for s in suivi], ["ecart-1"])
        self.assertEqual(len(refus), 2)


class Appliquer(Registre):
    def test_voie_besoin_exprimee_puis_notee(self):
        appels = []
        e = stratege.valider({"ecarts": [ecart(voie="besoin", besoin={"cle": "stats-reseaux", "manque": 3,
                                                                       "unite": "réseau"})]}, FICHES, CLES, set(), T)[1]
        faits, refus = stratege.appliquer(e, T, {}, exprimer=lambda *a: appels.append(a))
        self.assertEqual((len(faits), refus), (1, []))
        self.assertEqual(appels[0][:2], ("stratege", "stats-reseaux"))
        self.assertTrue(registre.decisions()[0]["decision"].startswith("écart (besoin)"))

    def test_besoin_refuse_n_est_pas_note(self):
        def refuse(*a):
            raise ValueError("clé invalide")
        e = stratege.valider({"ecarts": [ecart(voie="besoin", besoin={"cle": "X X", "manque": 1, "unite": "r"})]},
                             FICHES, CLES, set(), T)[1]
        faits, refus = stratege.appliquer(e, T, {}, exprimer=refuse)
        self.assertEqual(faits, [])
        self.assertIn("clé invalide", refus[0])
        self.assertEqual(registre.decisions(), [])

    def test_prediction_seulement_avec_mesure(self):
        e = stratege.valider({"ecarts": [ecart(mesure="cout_claude_semaine", attendu=20), ecart()]},
                             FICHES, CLES, set(), T)[1]
        stratege.appliquer(e, T, {"cout_claude_semaine": 30})
        d = registre.decisions()
        self.assertEqual((d[0]["mesure"], d[0]["avant"], d[0]["attendu"]), ("cout_claude_semaine", 30, 20))
        self.assertTrue(d[0]["echeance"])
        self.assertIsNone(d[1].get("echeance"))


class Suivi(Registre):
    def test_le_dernier_suivi_fait_foi(self):
        e = ecart() | {"id": "ecart-20261108-1"}
        self.jsonl("ecarts", [{"date": "2026-11-08T18:00:00+00:00", "ecarts": [e], "suivi": []},
                              {"date": "2026-11-14T18:00:00+00:00", "ecarts": [],
                               "suivi": [{"id": "ecart-20261108-1", "etat": "comble", "pourquoi": "issue #25"}]}])
        passes = stratege.ecarts_passes(T)
        self.assertEqual([(p["id"], p["etat"]) for p in passes], [("ecart-20261108-1", "comble")])

    def test_sans_suivi_l_ecart_reste_ouvert(self):
        self.jsonl("ecarts", [{"date": "2026-11-08T18:00:00+00:00", "ecarts": [ecart() | {"id": "e1"}]}])
        self.assertEqual(stratege.ecarts_passes(T)[0]["etat"], "ouvert")


class Empilement(Registre):
    """Un écart ouvert depuis 2 semaines s'empile : la Direction y répond, Jules le voit au bilan (Jules, 15/11)."""

    def ligne(self, date, *ids, suivi=()):
        return {"date": date, "ecarts": [ecart(constat=f"constat {i}") | {"id": i} for i in ids], "suivi": list(suivi)}

    def test_un_ecart_ouvert_ne_sort_jamais_de_la_vue(self):
        self.jsonl("ecarts", [self.ligne("2026-08-01T18:00:00+00:00", "vieux-ouvert", "vieux-comble"),
                              self.ligne("2026-08-08T18:00:00+00:00", suivi=[{"id": "vieux-comble", "etat": "comble"}])])
        self.assertEqual([e["id"] for e in suivi_ecarts.passes(T)], ["vieux-ouvert"])
        self.assertEqual([e["id"] for e in stratege.ecarts_passes(T)], ["vieux-ouvert"])

    def test_seuil_de_deux_semaines(self):
        self.jsonl("ecarts", [self.ligne("2026-10-25T18:00:00+00:00", "a"), self.ligne("2026-11-01T18:00:00+00:00", "b"),
                              self.ligne("2026-11-08T18:00:00+00:00", "c"),
                              self.ligne("2026-11-14T18:00:00+00:00", suivi=[{"id": "a", "etat": "abandonne"}])])
        self.assertEqual([(e["id"], e["semaines"]) for e in suivi_ecarts.qui_s_empilent(T)], [("b", 2)])

    def test_le_responsable_de_l_organisation_garde_un_poste_propose_ouvert(self):
        e = ecart(voie="poste", poste={"id": "repondeur"}) | {"id": "p"}
        self.jsonl("ecarts", [{"date": "2026-09-01T18:00:00+00:00", "ecarts": [e]}])
        self.assertEqual([p["id"] for p in ro.propositions_du_stratege(FICHES, T)], ["p"])

    def test_la_direction_doit_repondre(self):
        self.assertIn("ecarts_qui_s_empilent", direction.consigne_systeme())

    def test_le_bilan_du_lundi_et_le_message_telegram(self):
        lundi = datetime(2026, 11, 16, 6, 37, tzinfo=timezone.utc)
        with mock.patch("builtins.print"):
            texte, resume, _ = bilan.page(lundi, demandes=[], attente=[], fermees=[])
        self.assertNotIn("Écarts qui s'empilent", texte)
        self.assertNotIn("Stratège", resume)
        self.jsonl("ecarts", [self.ligne("2026-10-25T18:00:00+00:00", "a")])
        with mock.patch("builtins.print"):
            texte, resume, _ = bilan.page(lundi, demandes=[], attente=[], fermees=[])
        self.assertIn("### Écarts qui s'empilent", texte)
        self.assertIn("constat a (ouvert depuis 3 semaines, voie direction)", texte)
        self.assertIn("1 écart(s) du Stratège", resume)


class Branchements(Registre):
    def test_le_responsable_de_l_organisation_lit_les_postes_proposes(self):
        nouveau = {"id": "repondeur", "titre": "Répondeur"}
        self.jsonl("ecarts", [{"date": "2026-11-14T18:00:00+00:00", "ecarts": [
            ecart(voie="poste", poste=nouveau), ecart(voie="poste", poste={"id": "direction"}), ecart()]}])
        props = ro.propositions_du_stratege(FICHES, T)
        self.assertEqual([p["poste"]["id"] for p in props], ["repondeur"])

    def test_sans_poste_ne_compte_pas_le_responsable_de_l_organisation(self):
        self.assertNotIn("responsable_organisation", ro.sans_poste(T)["postes_qui_redigent_une_reponse"])

    def test_la_direction_lit_les_ecarts(self):
        self.assertIn("ecarts_du_stratege", direction.consigne_systeme())

    def test_la_seance_explique_les_trois_voies(self):
        seance = stratege.consigne_systeme()
        for voie in stratege.VOIES:
            self.assertIn(voie, seance)


if __name__ == "__main__":
    unittest.main()
