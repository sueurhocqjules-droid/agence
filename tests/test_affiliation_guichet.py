"""Responsable du revenu : demande de compte d'affiliation au guichet quand le besoin passe le délai sans option."""
import unittest

from agence import guichet
from agents import responsable_revenu as rr


def besoin(chaine, age=50, options=()):
    return {"id": f"responsable-revenu-{chaine}", "age_h": age, "delai_h": 48, "delai_depasse": age > 48,
            "options": list(options)}


def voie(chaine, nom="affiliation"):
    return {"chaine": chaine, "voie": nom, "besoin_id": f"responsable-revenu-{chaine}"}


class DemandeAffiliation(unittest.TestCase):
    def lancer(self, voies, dossier):
        appels = []

        def ecrire(titre, **kw):
            appels.append((titre, kw))
            return 10 + len(appels), True

        return rr.demander_comptes_affiliation(voies, None, dossier=dossier, ecrire=ecrire), appels

    def test_en_et_pt_sans_option_apres_le_delai(self):
        numeros, appels = self.lancer([voie("en"), voie("pt")], [besoin("en"), besoin("pt")])
        self.assertEqual(numeros, [11, 12])
        self.assertIn("Amazon Associates US", appels[0][0])
        self.assertIn("Amazon Associados Brasil", appels[1][0])
        self.assertEqual(appels[0][1]["par"], "responsable-revenu")

    def test_rien_avant_le_delai_ni_avec_une_option(self):
        self.assertEqual(self.lancer([voie("en")], [besoin("en", age=10)])[0], [])
        self.assertEqual(self.lancer([voie("en")], [besoin("en", options=[{"nom": "x"}])])[0], [])

    def test_rien_pour_une_autre_voie_ou_une_autre_chaine(self):
        self.assertEqual(self.lancer([voie("en", "audience")], [besoin("en")])[0], [])
        self.assertEqual(self.lancer([voie("es")], [besoin("es")])[0], [])

    def test_le_format_du_guichet_et_le_rappel_d_adresse(self):
        _, appels = self.lancer([voie("pt")], [besoin("pt")])
        kw = appels[0][1]
        texte = guichet.corps(kw["quoi"], kw["pourquoi"], kw["lien"], kw["debloque"], kw.get("cout", "0 €"))
        self.assertIn("**Quoi :**", texte)
        self.assertTrue(guichet.demande_de_compte(appels[0][0], kw["quoi"]))   # le rappel s'ajoute dans `demander`


if __name__ == "__main__":
    unittest.main()
