import unittest
from datetime import date, datetime, timedelta, timezone

from agents import analyste

BASE = {"vues_s1": 200.0, "cout_sujet": 3.0, "budget_semaine": 30.0, "creneaux_sujets": 8, "abonnes": 10,
        "abonnes_par_vue": 0.001, "vues_catalogue": 1000, "jours_stock": 0, "age_max": 30, "peu_de_donnees": True,
        "debut": date(2026, 11, 13)}


def amelioration(id_, mesure, gain, prix, poche="eur", **autres):
    return {"id": id_, "poste": "auteur", "lien": "https://exemple.org/outil", "source_gain": "https://exemple.org/prix",
            "prix": prix, "devise": "EUR" if poche == "eur" else "USD", "periode": "mois", "poche": poche,
            "mesure": mesure, "gain_annonce": gain, "unite": "jours" if mesure == "jours_stock" else "%", **autres}


class TestAnalyste(unittest.TestCase):
    def test_reference_seule_sans_amelioration(self):
        r = analyste.analyser(BASE, [], n=50)
        self.assertEqual(len(r["cas"]), 1)
        self.assertEqual(r["reference"]["cas"], ["reference"])
        self.assertEqual(r["reference"]["gain_eur_6_mois"], [0, 0, 0])
        self.assertEqual(r["propositions"]["eur"]["recommande"], [])
        self.assertIn("ne rien acheter", r["propositions"]["eur"]["pourquoi"])
        self.assertTrue(any("cas de référence seul" in l for l in analyste.resume(r, BASE)))

    def test_combinaison_non_additive(self):
        # 8 créneaux bloquent (le budget en paie 10) : baisser le coût seul ne rapporte rien, plus de créneaux seul
        # est vite rebloqué par le budget, les deux ensemble rapportent plus que la somme des deux seuls.
        moins_cher = amelioration("moins-cher", "cout_par_sujet", 50, 5)
        plus_de_creneaux = amelioration("plus-creneaux", "sujets_semaine", 100, 5)
        r = analyste.analyser(BASE, [moins_cher, plus_de_creneaux], n=200)
        seuls = {c["cas"][0]: c for c in r["cas"] if len(c["cas"]) == 1 and c["cas"] != ["reference"]}
        paire = next(c for c in r["cas"] if len(c["cas"]) == 2)
        self.assertEqual(seuls["moins-cher"]["gain_vues_6_mois"][1], 0)
        self.assertGreater(paire["gain_vues_6_mois"][1], paire["somme_des_seuls_vues_p50"])

    def test_palier_inutile_detecte(self):
        # Sans monétisation à 6 mois, plus de vues ne rapporte aucun euro : chaque palier est inutile, rien ne suffit.
        r = analyste.analyser(BASE, [amelioration("plus-de-vues", "vues", 20, 15)], n=100)
        lignes = {l["palier"]: l for l in r["paliers"]["eur"]}
        self.assertEqual(lignes[10]["cas"], [])
        self.assertEqual(lignes[20]["cas"], ["plus-de-vues"])
        self.assertGreater(lignes[20]["gain_vues_6_mois_p50"], 0)
        self.assertTrue(lignes[20]["inutile"])
        self.assertEqual(r["propositions"]["eur"]["montant_qui_suffit"], 0)

    def test_champ_libre_et_hors_liste_refuses(self):
        bonne = amelioration("ok", "vues", 10, 5)
        lignes = [bonne, amelioration("libre", "vues", 10, 5, commentaire="achetez vite"),
                  amelioration("mesure", "bonheur", 10, 5), amelioration("prix", "vues", 10, 0),
                  amelioration("Texte Libre ici", "vues", 10, 5), {**amelioration("poste", "vues", 10, 5), "poste": "x"},
                  {**amelioration("lien", "vues", 10, 5), "lien": "voir le site"}]
        self.assertEqual([a["id"] for a in analyste.lire_ameliorations(lignes, postes=["auteur"])], ["ok"])

    def test_cout_a_l_usage_et_change(self):
        a = amelioration("u", "vues", 10, 0.5, periode="usage")
        self.assertEqual(analyste.cout_mois(a, BASE), round(0.5 * 10 * 52 / 12, 2))
        b = amelioration("d", "vues", 10, 10, poche="claude_usd", devise="EUR")
        self.assertEqual(analyste.cout_mois(b, BASE), round(10 / analyste.EUR_PAR_USD, 2))

    def test_derniers_cas_et_section_du_bilan(self):
        from agents import bilan
        r = analyste.analyser(BASE, [amelioration("plus-de-vues", "vues", 20, 15)], n=50)
        lignes = [{"date": "2026-11-13T00:00:00+00:00", "type": "cas", **c} for c in r["cas"]]
        lignes += [{"date": "2026-11-13T00:00:00+00:00", "type": "proposition", **p} for p in r["propositions"].values()]
        lignes.insert(0, {"date": "2026-11-06T00:00:00+00:00", "type": "cas", "cas": ["ancien"], "roi_6_mois": 9})
        cas = analyste.derniers_cas(lignes)
        self.assertEqual(cas["ids"], ["plus-de-vues"])
        texte = "\n".join(bilan.investissements(cas, "aucun achat"))
        self.assertIn("## Investissements", texte)
        self.assertIn("Ne rien acheter (référence)", texte)
        self.assertIn("Proposition en € de ta poche : rien", texte)
        self.assertIn("Proposition en $ de ta limite Claude : rien", texte)
        self.assertIn("Prévu / réalisé : aucun achat", texte)
        self.assertIn("Pas encore de simulation", "\n".join(bilan.investissements({}, "aucun achat")))

    def test_direction_ne_propose_que_des_cas_simules(self):
        from agents import direction
        s = direction.schema(["chef-contenu"], ["plus-de-vues"])
        self.assertEqual(s["properties"]["investissements"]["items"]["properties"]["cas"]["items"]["enum"], ["plus-de-vues"])
        self.assertEqual(direction.schema(["chef-contenu"])["properties"]["investissements"]["items"]["properties"]["cas"],
                         {"type": "array", "maxItems": 0})
        reponse = {"decisions": [], "retours": [], "consignes": [], "questions": [], "investissements": [
            {"poche": "eur", "recommandation": "proposer_a_jules", "cas": ["achat-invente"], "pourquoi": "x"},
            {"poche": "claude_usd", "recommandation": "ne_rien_acheter", "cas": ["plus-de-vues"], "pourquoi": "x"}]}
        notes = []
        ancien = direction.registre.decider
        direction.registre.decider = lambda *a, **k: notes.append(a)
        try:
            faits, refus = direction.appliquer(reponse, datetime(2026, 11, 13, tzinfo=timezone.utc), {}, ["plus-de-vues"])
        finally:
            direction.registre.decider = ancien
        self.assertEqual(faits, [])
        self.assertEqual(len(refus), 2)

    def test_chercheur_prix_collecte_seulement(self):
        from agents import chercheur_outils as co
        prix = co.prix_boite("| Apify | https://apify.com/pricing : 5 $ de crédit, ensuite 19 $/mois |\n"
                             "| Rien | aucun lien, 3 €/mois |")
        self.assertEqual(prix, [{"lien": "https://apify.com/pricing", "prix": 19.0, "devise": "USD", "periode": "mois"}])
        source = "https://exemple.org/etude"
        bonne = {**amelioration("apify", "jours_stock", 3, 19.0, devise="USD"), "lien": "https://apify.com/pricing",
                 "source_gain": source}
        reponse = {"ameliorations": [bonne, {**bonne, "id": "cher", "prix": 25.0},
                                     {**bonne, "id": "invente", "lien": "https://inconnu.org/x"},
                                     {**bonne, "id": "libre", "avis": "génial"},
                                     {**bonne, "id": "sans-source", "source_gain": "https://ailleurs.org"}]}
        gardees, ecartees = co.valider_ameliorations(reponse, prix, {source}, {"auteur"}, set())
        self.assertEqual([a["id"] for a in gardees], ["apify"])
        self.assertEqual([e["id"] for e in ecartees], ["cher", "invente", "libre", "sans-source"])

    def test_prevu_realise(self):
        achat = datetime(2026, 10, 1, tzinfo=timezone.utc)
        investissements = [{"id": "outil", "date": achat.isoformat(), "mesure": "vues_semaine", "prevu": [100, 200, 400]}]
        valeurs = {achat + timedelta(weeks=4): 250, achat + timedelta(weeks=8): 50}
        r = analyste.prevu_realise(investissements, lambda m, a: valeurs[a], datetime(2026, 12, 1, tzinfo=timezone.utc))
        self.assertEqual(r[0]["s4"], {"mesure": 250, "dans_fourchette": True, "ecart_median": 50})
        self.assertFalse(r[0]["s8"]["dans_fourchette"])
        pas_encore = analyste.prevu_realise(investissements, lambda m, a: valeurs[a], achat + timedelta(weeks=5))
        self.assertIsNone(pas_encore[0]["s8"])


if __name__ == "__main__":
    unittest.main()
