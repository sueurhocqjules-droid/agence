import unittest

from agence import tri_mail


class TestTriMail(unittest.TestCase):
    def test_boite_vide_tout_manque(self):
        a_creer, manquantes, en_place = tri_mail.plan({}, [])
        self.assertEqual(a_creer, [])
        self.assertEqual(en_place, 0)
        self.assertEqual(manquantes, ["agence/en", "agence/es", "agence/pt", "agence/meta", "agence/plateformes"])

    def test_cree_seulement_les_filtres_absents(self):
        etiquettes = {"agence/es": "Label_1"}
        deja = [{"id": "f1", "criteria": {"to": "chaines+es@example.com "}, "action": {"addLabelIds": ["Label_1"]}}]
        a_creer, manquantes, en_place = tri_mail.plan(etiquettes, deja)
        self.assertEqual(en_place, 1)
        self.assertEqual([(n, c) for n, c, _ in a_creer], [("agence/es", tri_mail.REGLES[2][1])])
        self.assertNotIn("agence/es", manquantes)

    def test_meme_critere_autre_etiquette_a_creer(self):
        etiquettes = {"agence/es": "Label_1"}
        autre = [{"criteria": {"to": "chaines+es@example.com"}, "action": {"addLabelIds": ["Label_9"]}}]
        a_creer, _, en_place = tri_mail.plan(etiquettes, autre)
        self.assertEqual(en_place, 0)
        self.assertEqual(len(a_creer), 2)

    def test_filtres_n_ajoutent_qu_une_etiquette(self):
        for _, criteres, _ in tri_mail.REGLES:
            self.assertTrue(set(criteres) <= {"from", "to", "subject", "query", "negatedQuery"})

    def test_requete(self):
        self.assertEqual(tri_mail.requete({"to": "chaines+pt@example.com"}), "to:(chaines+pt@example.com)")
        self.assertEqual(tri_mail.requete(tri_mail.REGLES[2][1]),
                         'from:(youtube.com) ("Cada Segundo") -("A Cada Segundo")')


if __name__ == "__main__":
    unittest.main()
