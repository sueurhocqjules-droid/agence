"""Tests du Responsable du revenu et du Responsable de l'organisation (étape 12, sous-étapes 3, 14 et 18).

python -m unittest discover tests
"""
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agence import besoins, consignes, organisation, registre
from agents import responsable_organisation as ro
from agents import responsable_revenu as rr

T = datetime(2026, 11, 15, 18, tzinfo=timezone.utc)
CLES = {"GROQ_API_KEY", "GH_TOKEN"}


def palier(chaine, nom, criteres, progression):
    return {"chaine": chaine, "palier": nom, "atteint": False, "progression": progression,
            "criteres": [{"critere": c, "valeur": v, "cible": k} for c, v, k in criteres]}


PHOTO = {"date": "2026-11-15T12:00:00+00:00", "paliers": [
    palier("en", "yt_fans", [("abonnes", 600, 500), ("videos_90j", 40, 3), ("vues_shorts_90j", 15000, 3_000_000)], 0.005),
    palier("en", "yt_partenaire", [("abonnes", 600, 1000), ("vues_shorts_90j", 15000, 10_000_000)], 0.0015),
    palier("es", "yt_fans", [("abonnes", 0, 500), ("videos_90j", 40, 3), ("vues_shorts_90j", None, 3_000_000)], 0.0),
]}


class Registre(unittest.TestCase):
    """Registre dans un dossier temporaire."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ancien = registre.DOSSIER
        registre.DOSSIER = self.tmp

    def tearDown(self):
        registre.DOSSIER = self.ancien
        shutil.rmtree(self.tmp)


# --- Responsable du revenu -----------------------------------------------------------------------------------------

class Regles(unittest.TestCase):
    REGLES = [{"id": "a", "source": "https://a", "reperes": ["500 subscribers", "3 million"]},
              {"id": "b", "source": "https://b", "reperes": ["paid promotion"]},
              {"id": "c", "source": "https://c", "reperes": ["x"]},
              {"id": "d", "source": "https://d", "reperes": []}]

    def lire(self, adresse):
        if adresse == "https://c":
            raise TimeoutError("trop long")
        return {"https://a": "Needs 500 Subscribers and 3 MILLION views", "https://b": "nothing here"}[adresse]

    def test_etats(self):
        avant = {"c": {"confirmee_le": "2026-11-01"}}
        e = rr.verifier(avant, "2026-11-15", self.lire, self.REGLES)
        self.assertEqual(e["a"]["etat"], "confirmee")
        self.assertEqual(e["a"]["confirmee_le"], "2026-11-15")
        self.assertEqual(e["b"]["etat"], "a_relire")
        self.assertIn("paid promotion", e["b"]["detail"])
        self.assertEqual(e["c"]["etat"], "illisible")
        self.assertEqual(e["c"]["confirmee_le"], "2026-11-01")     # la dernière confirmation reste
        self.assertEqual(e["d"]["etat"], "a_verifier")

    def test_toute_regle_a_une_source_officielle(self):
        for r in rr.REGLES:
            self.assertTrue(r["source"].startswith("https://"), r["id"])
        for v in rr.VOIES.values():
            self.assertTrue(set(v["regles"]) <= {r["id"] for r in rr.REGLES})

    def test_page(self):
        e = rr.verifier({}, "2026-11-15", self.lire, self.REGLES[:1])
        page = rr.page_md(e, regles=[{**self.REGLES[0], "plateforme": "YouTube", "regle": "500 abonnés"}])
        self.assertIn("https://a", page)
        self.assertIn("confirmée", page)


class Distances(unittest.TestCase):
    def test_critere_en_retard_et_besoin(self):
        d = rr.distances(PHOTO)
        self.assertEqual(set(d), {"en", "es", "pt"})
        self.assertEqual(d["en"]["yt_fans"]["critere_en_retard"], "vues_shorts_90j")
        self.assertEqual(d["en"]["yt_fans"]["manque"], 2_985_000)
        self.assertEqual(d["en"]["yt_fans"]["a_multiplier_par"], 200)
        self.assertEqual(d["es"]["yt_fans"]["manque"], 500)       # 0 abonné ou vues inconnues : le premier à zéro
        phrase, manque, unite = rr.besoin_de("en", "yt_fans", d)
        self.assertEqual((manque, unite), (2_985_000, "vues Shorts sur 90 jours"))
        self.assertIn("2 985 000", phrase)

    def test_voie_sans_palier(self):
        phrase, manque, unite = rr.besoin_de("pt", "sponsoring", rr.distances(PHOTO))
        self.assertEqual(manque, 1)
        self.assertIn("Il manque la voie elle-même", phrase)
        self.assertEqual(rr.par_defaut("pt", rr.distances(PHOTO)), "affiliation")
        self.assertEqual(rr.par_defaut("en", rr.distances(PHOTO)), "yt_fans")

    def test_valider(self):
        dist = rr.distances(PHOTO)
        ligne, choix, ecartes = rr.valider({"ligne": "x", "voies": [
            {"chaine": "en", "voie": "yt_fans", "pourquoi": "le plus proche"},
            {"chaine": "en", "voie": "produit", "pourquoi": "doublon"},
            {"chaine": "es", "voie": "loterie", "pourquoi": "hors liste"},
            {"chaine": "fr", "voie": "yt_fans", "pourquoi": "chaîne inconnue"},
            {"chaine": "pt", "voie": "affiliation", "pourquoi": ""}]}, dist)
        self.assertEqual(choix, {"en": ("yt_fans", "le plus proche")})
        self.assertEqual(len(ecartes), 4)


ORIGINE_AUDIENCES = rr.audiences


class PassageRevenu(Registre):
    def test_ecrit_regles_besoins_et_decisions(self):
        (self.tmp / "seuils.json").write_text(json.dumps(PHOTO), encoding="utf-8")
        reponse = json.dumps({"ligne": "en est le plus proche", "voies": [
            {"chaine": "en", "voie": "yt_fans", "pourquoi": "600 abonnés sur 500"},
            {"chaine": "es", "voie": "sponsoring", "pourquoi": "aucun programme proche"}]})
        lire = lambda adresse: "500 subscribers 3 million last 90 days 1,000 subscribers 10 million February 1, 2027"  # noqa: E731
        resume, appel = rr.passage(False, lire=lire, demander=lambda poste, consigne: (reponse, "faux-modele"))
        self.assertTrue(appel)
        self.assertIn("voie(s) de revenu", resume)
        etat = json.loads((self.tmp / rr.ETAT).read_text(encoding="utf-8"))
        self.assertEqual(etat["yt_fans"]["etat"], "confirmee")
        self.assertEqual(etat["yt_inauthentique"]["etat"], "a_relire")
        self.assertIn("support.google.com", (self.tmp / rr.PAGE).read_text(encoding="utf-8"))
        ouverts = besoins.etat()
        self.assertEqual(ouverts["responsable-revenu-en"]["manque"], 2_985_000)
        self.assertEqual(ouverts["responsable-revenu-es"]["unite"], "voie de revenu ouverte (sponsoring)")
        self.assertIn("responsable-revenu-pt", ouverts)                 # pt : choisi par le script
        ligne = registre.lire_jsonl("revenu")[-1]
        self.assertTrue([v for v in ligne["voies"] if v["chaine"] == "pt"][0]["par_defaut"])
        decisions = [d["decision"] for d in registre.decisions()]
        self.assertIn("voie de revenu de la chaîne en : yt_fans", decisions)
        self.assertTrue(any(d.startswith("règle à relire") for d in decisions))
        # Deuxième passage, mêmes voies : ni nouveau besoin ni nouvelle décision de voie
        avant = len(registre.lire_jsonl("besoins")), len([d for d in decisions if d.startswith("voie")])
        rr.passage(False, lire=lire, demander=lambda poste, consigne: (reponse, "faux-modele"))
        decisions = [d["decision"] for d in registre.decisions()]
        self.assertEqual((len(registre.lire_jsonl("besoins")), len([d for d in decisions if d.startswith("voie")])),
                         avant)

    def test_audience_trop_basse_le_besoin_est_l_audience(self):
        (self.tmp / "seuils.json").write_text(json.dumps(PHOTO), encoding="utf-8")
        rr.audiences = lambda maintenant: {"en": 5000, "es": 5, "pt": 300}
        self.addCleanup(setattr, rr, "audiences", ORIGINE_AUDIENCES)
        reponse = json.dumps({"ligne": "x", "voies": [
            {"chaine": "en", "voie": "yt_fans", "pourquoi": "600 abonnés sur 500"},
            {"chaine": "es", "voie": "affiliation", "pourquoi": "pas de seuil"}]})
        rr.passage(False, lire=lambda a: "", demander=lambda p, c: (reponse, "faux-modele"))
        voies = {v["chaine"]: v for v in registre.lire_jsonl("revenu")[-1]["voies"]}
        self.assertEqual(voies["en"]["voie"], "yt_fans")
        self.assertEqual((voies["es"]["voie"], voies["es"]["unite"]), ("audience", "vues par semaine"))
        self.assertEqual(voies["es"]["manque"], rr.AUDIENCE_MIN - 5)
        self.assertEqual(besoins.etat()["responsable-revenu-es"]["unite"], "vues par semaine")
        d = {x["decision"]: x for x in registre.decisions()}["voie de revenu de la chaîne es : audience"]
        self.assertEqual((d["mesure"], d["avant"], d["attendu"]), ("vues_semaine:es", 5, rr.AUDIENCE_MIN))
        self.assertTrue(d["echeance"])
        self.assertEqual(d["voie"]["nouvelle"], "audience")

    def test_voie_jugee_fausse_est_defaite_et_interdite(self):
        (self.tmp / "seuils.json").write_text(json.dumps(PHOTO), encoding="utf-8")
        rr.audiences = lambda maintenant: {"en": 5000, "es": 5000, "pt": 5000}
        self.addCleanup(setattr, rr, "audiences", ORIGINE_AUDIENCES)
        avec = lambda voie: (json.dumps({"voies": [{"chaine": "es", "voie": voie, "pourquoi": "x"}]}), "m")  # noqa: E731
        rr.passage(False, lire=lambda a: "", demander=lambda p, c: avec("sponsoring"))
        rr.passage(False, lire=lambda a: "", demander=lambda p, c: avec("affiliation"))
        ident = [x for x in registre.decisions() if x["decision"].endswith("es : affiliation")][0]
        self.assertEqual(ident["voie"]["ancienne"], "sponsoring")
        registre.juger(ident["id"], "fausse", 10, "rien")
        self.assertIn("remise à sponsoring", rr.defaire(ident, "rien amélioré"))
        self.assertEqual(rr.derniere_voie()["es"], "sponsoring")
        self.assertEqual(rr.voies_defaites(), {"es": {"affiliation"}})
        rr.passage(False, lire=lambda a: "", demander=lambda p, c: avec("affiliation"))
        self.assertNotEqual(rr.derniere_voie()["es"], "affiliation")

    def test_essai_n_ecrit_rien(self):
        rr.passage(True, lire=lambda a: "", demander=lambda p, c: (_ for _ in ()).throw(RuntimeError("quota")))
        self.assertEqual(list(self.tmp.iterdir()), [])


# --- Responsable de l'organisation ---------------------------------------------------------------------------------

def fiche(texte=True, **k):
    f = {"titre": "T", "superieur": "direction", "statut": "en_service", "module": "agents.x",
         "reveil": "une fois par semaine", "equipe": [], "_scripts": [],
         "_texte": f"# T\n\n## {ro.SECTION}\nParce que.\n\n## Mission\nM." if texte else "# T\n\n## Mission\nM.",
         "_chiffres": {"suivi_par_le_lanceur": True, "passages_28j": 4, "passages_attendus_au_moins": 4}}
    f.update(k)
    return f


FICHES = {"direction": fiche(), "critique": fiche(), "veilleur": fiche(), "programmateur": fiche(_scripts=["creneaux"]),
          "neuf": fiche(_chiffres={"suivi_par_le_lanceur": True, "passages_28j": 0, "passages_attendus_au_moins": 0}),
          "nu": fiche(texte=False)}
SUPPRIMER = {"action": "supprimer", "postes": ["veilleur"], "pourquoi": "0 concept retenu en 4 semaines",
             "prediction": "rien ne baisse", "mesure": "vues_semaine", "attendu": "1000"}


class Chiffres(unittest.TestCase):
    def test_dimanches(self):
        lundi = datetime(2026, 11, 9, 10, tzinfo=timezone.utc)
        self.assertEqual(ro.seances_du_dimanche(lundi, lundi + timedelta(days=6)), 0)
        self.assertEqual(ro.seances_du_dimanche(lundi, datetime(2026, 11, 15, 18, tzinfo=timezone.utc)), 1)
        self.assertEqual(ro.seances_du_dimanche(datetime(2026, 11, 15, 18, tzinfo=timezone.utc), T + timedelta(days=7)), 1)

    def calcul(self, fiches, couts, maintenant=T):
        textes = {i: f"# T\n\n## {ro.SECTION}\nParce que.\n" for i in fiches}
        return ro.chiffres(fiches, {"creneaux": {"proprietaire": "programmateur"}}, couts, [], [], textes, maintenant)

    def test_registre_jeune_pas_de_faux_signal(self):
        couts = [{"debut": "2026-11-10T08:00:00Z", "agent": "stats", "dollars_equiv": "0", "appels_gratuits": "0",
                  "resultat": "ok"}]
        fiches = {"programmateur": {"statut": "en_service", "module": "agents.programmateur", "reveil": "une fois par semaine"},
                  "auteur": {"statut": "en_service", "reveil": "lundi 2h"},
                  "guetteur": {"statut": "en_service", "module": "agents.guetteur", "reveil": "à chaque réveil"}}
        samedi = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
        c = self.calcul(fiches, couts, samedi)
        self.assertIn("trop tôt pour le juger", c["programmateur"]["signaux"][0])
        self.assertIn("hors du lanceur", c["auteur"]["signaux"][0])
        self.assertIn("aucun passage alors qu'il en attendait au moins 4", c["guetteur"]["signaux"][0])
        self.assertEqual(c["programmateur"]["scripts"], ["creneaux"])
        # Un dimanche plus tard, le poste de la semaine qui n'a pas tourné est signalé
        c = self.calcul(fiches, couts, T)
        self.assertIn("en attendait au moins 1", c["programmateur"]["signaux"][0])

    def test_passages_echecs_et_section(self):
        couts = [{"debut": f"2026-11-1{i}T08:00:00Z", "agent": "creneaux", "dollars_equiv": "0.5",
                  "appels_gratuits": "2", "resultat": "echec : quota" if i < 3 else "ok"} for i in range(4)]
        c = self.calcul({"programmateur": {"statut": "en_service", "module": "m", "reveil": "une fois par semaine"}},
                        couts)["programmateur"]
        self.assertEqual((c["passages_28j"], c["echecs_28j"], c["dollars_claude_28j"], c["appels_gratuits_28j"]),
                         (4, 3, 2.0, 8))
        self.assertIn("3 échecs sur 4 passages", c["signaux"])
        sans = ro.chiffres({"x": {"statut": "en_service", "module": "m"}}, {}, couts, [], [], {"x": "# X"}, T)["x"]
        self.assertTrue(any("sans « Pourquoi ce poste existe »" in s for s in sans["signaux"]))


class Changement(unittest.TestCase):
    def refus(self, c, en_cours=None):
        return ro.refus_changement(c, FICHES, en_cours, CLES)

    def test_supprimer_valide(self):
        self.assertIsNone(self.refus(SUPPRIMER))

    def test_garde_fous(self):
        self.assertIn("intouchable", self.refus({**SUPPRIMER, "postes": ["critique"]}))
        self.assertIn("section", self.refus({**SUPPRIMER, "postes": ["nu"]}))
        self.assertIn("trop tôt", self.refus({**SUPPRIMER, "postes": ["neuf"]}))
        self.assertIn("scripts", self.refus({**SUPPRIMER, "postes": ["programmateur"]}))
        self.assertIn("existant", self.refus({**SUPPRIMER, "postes": ["inconnu"]}))
        self.assertIn("prédiction", self.refus({**SUPPRIMER, "prediction": ""}))
        self.assertIn("hors liste", self.refus({**SUPPRIMER, "action": "renommer"}))
        self.assertIn("déjà en essai", self.refus(SUPPRIMER, {"echeance": "2026-12-01T00:00:00"}))
        # Fusion : le poste absorbé (le dernier) passe les mêmes contrôles, pas celui qui reste
        self.assertIsNone(self.refus({**SUPPRIMER, "action": "fusionner", "postes": ["critique", "programmateur"]}))
        self.assertIn("intouchable", self.refus({**SUPPRIMER, "action": "fusionner", "postes": ["veilleur", "critique"]}))

    def test_creer(self):
        nouveau = {"id": "redacteur-reponses", "titre": "Rédacteur", "superieur": "direction", "mission": "Répondre.",
                   "cles": ["GROQ_API_KEY"]}
        creer = {**SUPPRIMER, "action": "creer", "postes": [], "nouveau": nouveau}
        self.assertIsNone(self.refus(creer))
        self.assertIn("existe déjà", self.refus({**creer, "nouveau": {**nouveau, "id": "veilleur"}}))
        self.assertIn("identifiant", self.refus({**creer, "nouveau": {**nouveau, "id": "Poste Neuf"}}))
        self.assertIn("supérieur", self.refus({**creer, "nouveau": {**nouveau, "superieur": "jules"}}))
        self.assertIn("clé", self.refus({**creer, "nouveau": {**nouveau, "cles": ["META_TOKEN"]}}))

    def test_valider(self):
        ligne, avis, changement, ecartes = ro.valider({"ligne": "x", "avis": [
            {"poste": "veilleur", "avis": "surveiller", "pourquoi": "0 concept"},
            {"poste": "veilleur", "avis": "garder", "pourquoi": "doublon"},
            {"poste": "inconnu", "avis": "garder", "pourquoi": "?"},
            {"poste": "critique", "avis": "virer", "pourquoi": "hors liste"}],
            "changement": {**SUPPRIMER, "postes": ["critique"]}}, FICHES, None, CLES)
        self.assertEqual([a["poste"] for a in avis], ["veilleur"])
        self.assertIsNone(changement)
        self.assertEqual(len(ecartes), 4)
        _, _, changement, _ = ro.valider({"changement": SUPPRIMER}, FICHES, None, CLES)
        self.assertEqual((changement["mesure"], changement["attendu"]), ("vues_semaine", 1000.0))


class Appliquer(Registre):
    def setUp(self):
        super().setUp()
        self.appels = []

    def faux(self, nom, retour):
        return lambda *a, **k: self.appels.append((nom, a)) or retour

    def test_supprimer(self):
        c = ro.nettoyer(SUPPRIMER)
        fait = ro.appliquer(c, FICHES, T, donnees_mesures={}, demander_ing=self.faux("ing", 42),
                            demander_guichet=self.faux("guichet", (7, True)), pause=self.faux("pause", None))
        self.assertEqual([n for n, _ in self.appels], ["pause", "ing"])
        self.assertEqual(self.appels[0][1][:2], ("veilleur", ro.POSTE))
        self.assertIn("statut", self.appels[1][1][1])
        d = registre.decisions()[-1]
        self.assertEqual(d["auteur"], "responsable-organisation")     # le mail du lundi les liste par auteur
        self.assertTrue(d["decision"].startswith("changement de poste"))
        self.assertEqual(d["echeance"][:10], "2026-12-13")
        self.assertIn("demande à l'Ingénierie #42", fait)
        self.assertEqual(ro.changement_en_cours(registre.decisions(), T)["echeance"][:10], "2026-12-13")
        self.assertIsNone(ro.changement_en_cours(registre.decisions(), T + timedelta(days=29)))

    def test_creer_demande_les_cles_au_guichet(self):
        c = ro.nettoyer({**SUPPRIMER, "action": "creer", "postes": [], "mesure": None,
                         "nouveau": {"id": "redacteur", "titre": "Rédacteur", "superieur": "direction",
                                     "mission": "Répondre.", "cles": ["GROQ_API_KEY"]}})
        fait = ro.appliquer(c, FICHES, T, demander_ing=self.faux("ing", None),
                            demander_guichet=self.faux("guichet", (None, False)), pause=self.faux("pause", None))
        self.assertEqual([n for n, _ in self.appels], ["ing", "guichet"])
        self.assertIn("GROQ_API_KEY", self.appels[1][1][1])
        self.assertIn("demande à l'Ingénierie non envoyée (essai)", fait)


class PassageOrganisation(Registre):
    def test_essai_n_ecrit_rien_et_modele_en_panne(self):
        def panne(poste, consigne):
            raise RuntimeError("quota")
        resume, appel = ro.passage(True, demander=panne, maintenant=T)
        self.assertFalse(appel)
        self.assertIn("aucun changement", resume)
        self.assertEqual(list(self.tmp.iterdir()), [])

    def test_passage_note_le_rapport(self):
        reponse = json.dumps({"ligne": "tout va", "avis": [{"poste": "veilleur", "avis": "garder", "pourquoi": "ok"}],
                              "changement": None})
        ro.passage(False, demander=lambda p, c: (reponse, "faux-modele"), maintenant=T)
        ligne = registre.lire_jsonl("organisation")[-1]
        self.assertEqual((ligne["par"], ligne["ligne"], ligne["changement"]), (ro.POSTE, "tout va", None))


# --- Toutes les fiches ---------------------------------------------------------------------------------------------

class Fiches(unittest.TestCase):
    def test_chaque_fiche_dit_pourquoi_le_poste_existe(self):
        for ident in organisation.fiches():
            texte = consignes.chemin_fiche(ident).read_text(encoding="utf-8")
            self.assertIn(f"## {ro.SECTION}", texte, ident)
            self.assertTrue(consignes.lire_section(texte, ro.SECTION).strip(), ident)

    def test_intouchables_existent(self):
        self.assertTrue(set(ro.INTOUCHABLES) <= set(organisation.fiches()))


if __name__ == "__main__":
    unittest.main()
