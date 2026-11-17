"""Règles restantes de l'étape 12 (sous-étapes 4, 12, 13 et 19) : rappel d'une adresse distincte, dérogation sur les
comptes, « Décider vite » appliqué par le code, concepts sans plafond.

python -m unittest discover tests
"""
import json
import os
import re
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from agence import besoins, catalogue, delais, guichet, lancer, organisation, registre
from agents import bilan, direction, veilleur

RACINE = Path(__file__).resolve().parent.parent
T = datetime(2026, 11, 17, 12, tzinfo=timezone.utc)
LIBRE = {"date": "2026-11-14T10:00:00+00:00", "etat": "propose", "nom": "Modèle libre", "lien": "https://openrouter.ai/x/libre",
         "remplace": "auteur", "pourquoi": "écrit un sujet sans Claude", "compte_requis": False, "essai": "écrire un sujet",
         "economie_usd_semaine": 12, "besoin": "programmateur-sujets"}
COMPTE = {**LIBRE, "nom": "GPU gratuit", "lien": "https://gpu.example/offre", "compte_requis": True}


def besoin(ident="programmateur-sujets", date_="2026-11-15T10:00:00+00:00", **plus):
    par, _, cle = ident.partition("-")
    return {"id": ident, "date": date_, "par": par, "cle": cle, "besoin": "il manque des sujets", "manque": 27,
            "unite": "sujets par semaine", "pourquoi": "plus de vues", "etat": "ouvert", **plus}


class FauxGitHub:
    def __init__(self, issues=()):
        self.issues, self.appels = list(issues), []

    def __call__(self, *args, entree=None):
        self.appels.append((args, entree))
        if args[:1] == ("api",):
            return json.dumps(self.issues)
        if args[:2] == ("issue", "create"):
            return "https://github.com/x/agence/issues/77\n"
        return ""

    def creees(self):
        return [(a, e) for a, e in self.appels if a[:2] == ("issue", "create")]


class Registre(unittest.TestCase):
    """Registre, catalogue et état du guichet dans un dossier temporaire."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.anciens = registre.DOSSIER, catalogue.CATALOGUE, guichet.ETAT
        registre.DOSSIER, catalogue.CATALOGUE, guichet.ETAT = self.tmp, self.tmp / "catalogue.md", self.tmp / "guichet.json"
        catalogue.CATALOGUE.write_text("| Ressource |\n|---|\n", encoding="utf-8")
        for p in (mock.patch("builtins.print"), mock.patch.dict(os.environ, {"AGENCE_ESSAI": ""})):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        registre.DOSSIER, catalogue.CATALOGUE, guichet.ETAT = self.anciens
        shutil.rmtree(self.tmp)

    def ecrire(self, nom, lignes):
        with open(self.tmp / f"{nom}.jsonl", "a", encoding="utf-8") as f:
            for l in lignes:
                f.write(json.dumps(l, ensure_ascii=False) + "\n")

    def lignes(self, nom):
        chemin = self.tmp / f"{nom}.jsonl"
        return [json.loads(l) for l in chemin.read_text(encoding="utf-8").splitlines()] if chemin.exists() else []


# --- Sous-étape 4 : rappel d'une adresse distincte ---------------------------------------------------------------

class AdresseDistincte(Registre):
    def test_une_demande_de_compte_porte_le_rappel_de_la_surete(self):
        gh = FauxGitHub()
        guichet.demander("Compte Pexels", "Créer un compte Pexels", "images libres", "3 vignettes", "chef-contenu", gh=gh)
        (_, texte), = gh.creees()
        self.assertIn(guichet.RAPPEL_ADRESSE, texte)
        self.assertIn("adresse distincte", guichet.RAPPEL_ADRESSE)
        self.assertLess(texte.index("**Coût :**"), texte.index(guichet.RAPPEL_ADRESSE))   # après le format fixe

    def test_une_demande_sans_compte_ne_le_porte_pas(self):
        gh = FauxGitHub()
        guichet.demander("Droit d'envoi Gmail", "poser un jeton gmail.send", "envoyer les messages validés",
                         "les contacts", "contacts", gh=gh)
        self.assertNotIn("Rappel de la Sûreté", gh.creees()[0][1])

    def test_ce_qui_compte_comme_une_demande_de_compte(self):
        for titre in ("Compte pour l'outil GPU gratuit", "Comptes de la nouvelle chaîne Fruits", "Ouvrir une nouvelle chaine",
                      "Créer la chaîne Fruits qui parlent"):
            self.assertTrue(guichet.demande_de_compte(titre), titre)
        for titre in ("Accès au serveur Oracle", "Clé de l'API météo pour la chaîne es", "Décompte des vues"):
            self.assertFalse(guichet.demande_de_compte(titre), titre)

    def test_l_outil_avec_compte_du_catalogue_recoit_le_rappel(self):
        gh = FauxGitHub()
        catalogue.retenir(COMPTE, "la Direction", "calcul gratuit",
                          vers_guichet=lambda *a, **k: guichet.demander(*a, gh=gh, **k))
        self.assertIn(guichet.RAPPEL_ADRESSE, gh.creees()[0][1])

    def test_les_comptes_d_une_nouvelle_chaine_font_une_seule_demande_urgente(self):
        gh = FauxGitHub()
        numero, nouvelle = guichet.demander_comptes("Fruits qui parlent", ["youtube", "tiktok", "tiktok"],
                                                    "concept à 12 fois la médiane", "la Direction", "des fruits", gh=gh)
        self.assertEqual((numero, nouvelle), (77, True))
        (args, texte), = gh.creees()
        self.assertEqual(args[args.index("--label") + 1], "guichet,urgent")
        self.assertIn("youtube, tiktok)", texte)
        self.assertIn(guichet.RAPPEL_ADRESSE, texte)

    def test_une_chaine_sans_reseau_connu_est_refusee(self):
        with self.assertRaises(ValueError):
            guichet.demander_comptes("Fruits", ["myspace"], "p", "la Direction", gh=FauxGitHub())

    def test_la_fiche_de_la_surete_porte_la_regle(self):
        fiche = (RACINE / "organisation" / "postes" / "surete.md").read_text(encoding="utf-8")
        self.assertIn("adresse distincte", fiche)
        self.assertIn("agence/guichet.py", fiche)


class NouvelleChaine(Registre):
    def test_le_schema_de_la_direction_ouvre_une_chaine_sur_des_reseaux_connus(self):
        s = direction.schema(["chef-contenu"])
        self.assertIn("chaines", s["required"])
        chaines = s["properties"]["chaines"]
        self.assertEqual(chaines["maxItems"], direction.CHAINES_MAX)
        self.assertEqual(chaines["items"]["properties"]["reseaux"]["items"]["enum"], list(guichet.RESEAUX))
        self.assertIn("- chaines :", direction.consigne_systeme())

    def test_une_nouvelle_chaine_devient_une_demande_de_comptes_et_une_decision(self):
        recus = []
        reponse = {"chaines": [{"nom": "Fruits qui parlent", "concept": "des fruits", "reseaux": ["youtube", "tiktok"],
                                "pourquoi": "12 fois la médiane"}],
                   "decisions": [], "retours": [], "consignes": [], "questions": []}
        with mock.patch.object(guichet, "demander_comptes", lambda *a, **k: recus.append(a) or (31, True)):
            faits, refus = direction.appliquer(reponse, T, {})
        self.assertEqual(refus, [])
        self.assertEqual(recus[0][:2], ("Fruits qui parlent", ["youtube", "tiktok"]))
        self.assertIn("nouvelle chaîne : Fruits qui parlent", faits[0])
        (d,) = self.lignes("decisions")
        self.assertEqual(d["auteur"], "direction")
        self.assertIn("(#31)", d["decision"])

    def test_chaque_concept_recoit_un_verdict_et_seul_a_creuser_revient(self):
        concepts = [{"date": "2026-11-15T22:00:00+00:00", "lien": f"https://y/{i}", "concept": f"c{i}", "etat": "propose"}
                    for i in range(3)]
        (self.tmp / "concepts.jsonl").write_text("".join(json.dumps(c) + "\n" for c in concepts), encoding="utf-8")
        ouverts = direction.concepts_a_trancher()
        self.assertEqual([c["lien"] for c in ouverts], ["https://y/0", "https://y/1", "https://y/2"])
        s = direction.schema(["chef-contenu"], concepts=[c["lien"] for c in ouverts])
        self.assertIn("concepts", s["required"])
        self.assertEqual(s["properties"]["concepts"]["items"]["properties"]["argent"]["enum"], list(direction.ARGENT))
        v = lambda lien, verdict, argent="viral": {"lien": lien, "verdict": verdict, "argent": argent, "piste": "p",
                                                   "pourquoi": "w"}
        reponse = {"concepts": [v("https://y/0", "nouvelle_chaine"), v("https://y/1", "a_creuser", "affiliation"),
                                v("https://inconnu", "ecarte")],
                   "decisions": [], "retours": [], "consignes": [], "questions": []}
        faits, refus = direction.appliquer(reponse, T, {})
        self.assertEqual(len([f for f in faits if f.startswith("concept ")]), 2)
        self.assertTrue(any("hors liste" in r for r in refus))
        self.assertTrue(any("1 concept(s) sans verdict" in r for r in refus))   # https://y/2 oublié
        restants = direction.concepts_a_trancher()
        self.assertEqual([c["lien"] for c in restants], ["https://y/1", "https://y/2"])
        self.assertEqual(restants[0]["dernier_verdict"]["piste"], "p")

    def test_une_demande_refusee_est_notee_sans_arreter_la_seance(self):
        reponse = {"chaines": [{"nom": "X", "concept": "c", "reseaux": ["myspace"], "pourquoi": "p"}],
                   "decisions": [], "retours": [], "consignes": [], "questions": []}
        faits, refus = direction.appliquer(reponse, T, {})
        self.assertEqual(faits, [])
        self.assertIn("nouvelle chaîne X", refus[0])


# --- Sous-étape 12 : dérogation sur la création des comptes ------------------------------------------------------

class Derogation(Registre):
    def test_la_date_du_vrai_fichier_est_un_lundi_de_fin_decembre(self):
        prevu = guichet.derogation(date(2026, 12, 28))
        self.assertEqual(prevu, date(2026, 12, 28))
        self.assertEqual(prevu.weekday(), 0)

    def test_elle_ne_vaut_que_la_semaine_de_ce_bilan(self):
        self.assertIsNone(guichet.derogation(date(2026, 12, 21)))
        self.assertIsNone(guichet.derogation(date(2027, 1, 4)))
        self.assertIsNone(guichet.derogation(datetime(2026, 11, 16, 7, tzinfo=timezone.utc)))

    def test_jules_l_avance_en_changeant_la_date(self):
        seuils = {"derogation": {"bilan": date(2026, 11, 30)}}
        self.assertEqual(guichet.derogation(date(2026, 11, 30), seuils), date(2026, 11, 30))
        self.assertIsNone(guichet.derogation(date(2026, 12, 28), seuils))
        self.assertIsNone(guichet.derogation(date(2026, 12, 28), {}))

    def test_la_preuve_est_la_liste_des_comptes_deja_traites(self):
        def issue(numero, titre, ferme):
            return {"number": numero, "title": titre, "body": "", "html_url": f"https://x/{numero}", "state": "closed" if ferme else "open",
                    "created_at": "2026-11-20T08:00:00Z", "closed_at": "2026-11-22T08:00:00Z" if ferme else None,
                    "labels": [{"name": "guichet"}], "user": {"login": guichet.ROBOT}}
        gh = FauxGitHub([issue(1, "Compte Pexels", True), issue(2, "Compte Suno", False), issue(3, "Accès Oracle", True)])
        self.assertEqual(guichet.comptes_traites(gh), [{"numero": 1, "titre": "Compte Pexels", "ouverte_le": "2026-11-20",
                                                        "fermee_le": "2026-11-22"}])

    def test_la_direction_ne_la_lit_que_la_semaine_prevue(self):
        self.assertEqual(direction.derogation_comptes(datetime(2026, 11, 16, tzinfo=timezone.utc), traites=[]), {})
        d = direction.derogation_comptes(datetime(2026, 12, 28, tzinfo=timezone.utc), traites=[{"numero": 1}])
        self.assertEqual(d["derogation_comptes"]["demandes_de_compte_traitees_par_jules"], [{"numero": 1}])
        self.assertIn("derogation_comptes", direction.consigne_systeme())


class DerogationAuBilan(unittest.TestCase):
    def test_le_bilan_prevu_l_annonce_dans_a_valider_et_pas_les_autres(self):
        def a_valider(maintenant):
            texte = bilan.page(maintenant, demandes=[], attente=[], fermees=[])[0]
            return texte.split(f"## {bilan.ORDRE[0]}")[1].split(f"## {bilan.ORDRE[1]}")[0]
        self.assertIn("Création des comptes", a_valider(datetime(2026, 12, 28, 7, tzinfo=timezone.utc)))
        self.assertNotIn("Création des comptes", a_valider(datetime(2026, 11, 16, 7, tzinfo=timezone.utc)))


# --- Sous-étape 13 : « Décider vite » appliqué par le code ---------------------------------------------------------

class DepartEnEssai(Registre):
    def setUp(self):
        super().setUp()
        self.demandes = []

    def retenir(self, c, par, pourquoi):
        return catalogue.retenir(c, par, pourquoi,
                                 vers_ingenierie=lambda *a: self.demandes.append(a) or 41 + len(self.demandes))

    def test_au_bout_de_48_h_l_option_gratuite_sans_compte_part_en_essai(self):
        self.ecrire("besoins", [besoin()])                       # écrit il y a 50 h
        self.ecrire("candidats", [COMPTE, LIBRE])
        faits, refus = delais.partir(T, self.retenir)
        self.assertEqual((len(faits), refus), (1, []))
        (demande,) = self.demandes
        self.assertIn("Modèle libre", demande[0])
        self.assertEqual(demande[3], "programmateur")             # au nom du poste qui a le besoin (classe 1)
        (d,) = self.lignes("decisions")
        self.assertEqual(d["auteur"], "programmateur")
        self.assertIn("départ en essai au bout de 48 h", d["decision"])
        self.assertIn("(issue #42)", d["decision"])
        (c,) = self.lignes("catalogue")
        self.assertEqual((c["voie"], c["besoin"]), ("essai", "programmateur-sujets"))

    def test_rien_ne_part_avant_48_h(self):
        self.ecrire("besoins", [besoin(date_="2026-11-15T13:00:00+00:00")])   # 47 h
        self.ecrire("candidats", [LIBRE])
        self.assertEqual(delais.partir(T, self.retenir), ([], []))
        self.assertEqual(self.demandes, [])

    def test_une_option_avec_compte_ne_part_jamais_seule(self):
        self.ecrire("besoins", [besoin()])
        self.ecrire("candidats", [COMPTE])
        self.assertEqual(delais.partir(T, self.retenir), ([], []))
        self.assertEqual(self.lignes("catalogue"), [])

    def test_le_meme_outil_ne_part_pas_deux_fois_et_le_suivant_attend_48_h(self):
        autre = {**LIBRE, "nom": "Autre modèle", "lien": "https://openrouter.ai/x/autre"}
        self.ecrire("besoins", [besoin()])
        self.ecrire("candidats", [LIBRE, autre])
        with mock.patch.object(registre, "maintenant", lambda: T.isoformat(timespec="seconds")):
            delais.partir(T, self.retenir)
        self.assertEqual(delais.partir(T + timedelta(hours=6), self.retenir), ([], []))
        self.assertEqual(len(self.demandes), 1)
        self.assertIn("Autre modèle", self.demandes[0][0])               # la trouvaille la plus récente d'abord
        faits, _ = delais.partir(T + timedelta(hours=49), self.retenir)   # l'essai n'a pas comblé le besoin : le suivant
        self.assertIn("Modèle libre", faits[0])

    def test_un_depart_par_passage_le_plus_ancien_besoin_d_abord(self):
        autre = {**LIBRE, "nom": "Voix libre", "lien": "https://github.com/a/voix", "besoin": "auteur-voix"}
        self.ecrire("besoins", [besoin(), besoin("auteur-voix", "2026-11-14T10:00:00+00:00")])
        self.ecrire("candidats", [LIBRE, autre])
        faits, _ = delais.partir(T, self.retenir)
        self.assertEqual(len(faits), min(2, delais.DEPARTS_MAX))
        self.assertIn("auteur-voix", faits[0])

    def test_un_depart_refuse_est_dit_et_ne_laisse_aucune_decision(self):
        self.ecrire("besoins", [besoin()])
        self.ecrire("candidats", [LIBRE])

        def refuse(c, par, pourquoi):
            raise ValueError("budget de l'Ingénierie atteint")
        faits, refus = delais.partir(T, refuse)
        self.assertEqual(faits, [])
        self.assertIn("budget de l'Ingénierie atteint", refus[0])
        self.assertEqual(self.lignes("decisions"), [])

    def test_en_essai_a_blanc_rien_n_est_ecrit(self):
        self.ecrire("besoins", [besoin()])
        self.ecrire("candidats", [LIBRE])
        with mock.patch.dict(os.environ, {"AGENCE_ESSAI": "1"}):
            faits, _ = delais.partir(T, lambda c, par, pq: catalogue.retenir(c, par, pq, vers_ingenierie=lambda *a: None))
        self.assertEqual(len(faits), 1)
        self.assertEqual((self.lignes("decisions"), self.lignes("catalogue")), ([], []))


class MesureDesDelais(Registre):
    def test_un_besoin_ouvert_depuis_plus_de_72_h_est_en_retard(self):
        self.ecrire("besoins", [besoin(date_="2026-11-14T04:00:00+00:00"), besoin("auteur-voix", "2026-11-16T12:00:00+00:00")])
        m = delais.mesure(T)
        self.assertEqual(m["en_retard"], ["programmateur-sujets"])
        self.assertEqual({l["id"]: (l["classe"], l["cible_h"], l["delai_h"]) for l in m["besoins"]},
                         {"programmateur-sujets": (1, 72, 80), "auteur-voix": (1, 72, 24)})
        self.assertEqual(delais.phrases_retard(m), ["besoin programmateur-sujets ouvert depuis 80 h (cible 72 h)"])

    def test_un_besoin_comble_donne_le_delai_de_mise_en_service(self):
        self.ecrire("besoins", [besoin(date_="2026-11-14T10:00:00+00:00"),
                                besoin(date_="2026-11-16T12:00:00+00:00", etat="clos", raison="comblé : il ne manque plus rien"),
                                besoin("auteur-voix", "2026-11-14T10:00:00+00:00"),
                                besoin("auteur-voix", "2026-11-15T10:00:00+00:00", etat="clos", raison="abandonné")])
        m = delais.mesure(T)
        self.assertEqual([(l["id"], l["etat"], l["delai_h"], l["en_retard"]) for l in m["besoins"]],
                         [("programmateur-sujets", "en service", 50, False)])
        self.assertEqual((m["mis_en_service"], m["delai_median_h"], m["en_retard"]), (1, 50, []))

    def test_une_voie_avec_compte_a_une_semaine(self):
        self.ecrire("besoins", [besoin(date_="2026-11-13T12:00:00+00:00")])   # 96 h
        self.ecrire("catalogue", [{"date": "2026-11-15T10:00:00+00:00", "lien": COMPTE["lien"], "voie": "guichet",
                                   "besoin": "programmateur-sujets"}])
        m = delais.mesure(T)
        self.assertEqual((m["besoins"][0]["classe"], m["besoins"][0]["cible_h"], m["en_retard"]), (2, 168, []))


class Coherence(unittest.TestCase):
    """Le document suit le réel : la mission, les fiches, les scripts et les workflows disent la même chose."""

    def test_les_delais_du_code_sont_ceux_de_la_mission(self):
        mission = (RACINE / "organisation" / "MISSION.md").read_text(encoding="utf-8")
        self.assertIn(f"un besoin a un délai ({besoins.DELAI_H} h par défaut) et au plus {besoins.OPTIONS_MAX} options", mission)
        self.assertIn(f"cible {delais.CIBLE_H[1]} h en classe 1, une semaine en classe 2", mission)
        self.assertEqual(delais.CIBLE_H[2], 7 * 24)

    def test_chaque_script_a_un_proprietaire_en_service(self):
        postes = organisation.fiches()
        for nom, s in organisation.scripts().items():
            self.assertIn(s.get("proprietaire"), postes, f"script {nom} : propriétaire sans fiche")
            self.assertEqual(postes[s["proprietaire"]]["statut"], "en_service", f"script {nom} : propriétaire hors service")

    def test_tout_ce_que_les_workflows_lancent_existe(self):
        postes, scripts = organisation.fiches(), organisation.scripts()
        lances = set()
        for chemin in (RACINE / ".github" / "workflows").glob("*.yml"):
            lances |= set(re.findall(r"python -m agence\.lancer ([a-z][a-z0-9_-]*)", chemin.read_text(encoding="utf-8")))
        self.assertIn("delais", lances)
        for nom in sorted(lances):
            lancer.preparer(nom, postes, scripts)   # lève ValueError si ni agent construit ni script

    def test_le_script_des_delais_est_branche_au_reveil_avec_son_jeton(self):
        scripts = organisation.scripts()
        self.assertIn("delais", organisation.fiches()[scripts["delais"]["proprietaire"]]["scripts"])
        self.assertEqual(organisation.cles_accordees("delais", scripts["delais"]["secrets"]), ({"GH_TOKEN"}, []))
        reveil = (RACINE / ".github" / "workflows" / "reveil.yml").read_text(encoding="utf-8")
        self.assertIn("python -m agence.lancer delais partir", reveil)
        self.assertRegex(reveil, r"actions: write")   # sans lui, la demande est écrite mais l'Ingénierie ne part pas


# --- Sous-étape 19 : concepts sans plafond ------------------------------------------------------------------------

class Concepts(unittest.TestCase):
    def fiche(self, i, **plus):
        return {"lien": f"https://www.youtube.com/shorts/{i:011d}", "concept": "c", "pourquoi_ca_marche": "p",
                "adaptation": "a", "effort": "comme nos sujets", "langues": ["en"], **plus}

    def montres(self, n):
        return [{"lien": f"https://www.youtube.com/shorts/{i:011d}", "titre": "t", "chaine": "x", "vues": 900,
                 "mediane_chaine": 100, "ratio": 9.0} for i in range(n)]

    def test_le_veilleur_garde_tous_les_concepts_realisables_qu_il_a_lus(self):
        n = veilleur.MONTRES_AU_MODELE
        gardes, ecartes = veilleur.valider({"fiches": [self.fiche(i) for i in range(n)]}, self.montres(n), 3.74, set())
        self.assertEqual((len(gardes), ecartes), (n, []))
        self.assertGreater(n, 5)
        self.assertNotIn("Garde au plus", veilleur.consigne(self.montres(1)))

    def test_un_concept_dit_s_il_va_sur_une_nouvelle_chaine(self):
        fiches = [self.fiche(0, destination="nouvelle chaîne"), self.fiche(1), self.fiche(2, destination="ailleurs")]
        gardes, _ = veilleur.valider({"fiches": fiches}, self.montres(3), 3.74, set())
        self.assertEqual([g["destination"] for g in gardes], ["nouvelle chaîne", "chaîne existante", "chaîne existante"])
        self.assertIn("nouvelle chaîne", veilleur.consigne(self.montres(1)))

    def test_les_tendances_se_lisent_hors_du_creneau_sans_mot_cle(self):
        appels = []

        def appel(ressource, **params):
            appels.append(params)
            if params["relevanceLanguage"] == "es":
                raise RuntimeError("YouTube search : HTTP 403")
            return {"items": [{"id": {"videoId": f"vid-{params['relevanceLanguage']}"}}, {"id": {}}]}
        with mock.patch("builtins.print"):
            ids = veilleur.tendances(T, appel)
        self.assertEqual(ids, ["vid-en", "vid-pt"])               # une langue refusée ne casse pas les autres
        self.assertTrue(all("q" not in p and p["videoDuration"] == "short" for p in appels))

    def test_les_fiches_disent_que_rien_ne_plafonne_les_concepts(self):
        fiche = (RACINE / "organisation" / "postes" / "veilleur.md").read_text(encoding="utf-8")
        self.assertIn("sans plafond", fiche)
        self.assertNotIn("5 au plus par semaine", fiche)
        self.assertIn("aucune limite au nombre de concepts", direction.consigne_systeme())


if __name__ == "__main__":
    unittest.main()
