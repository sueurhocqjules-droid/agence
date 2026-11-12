"""Courrier : lecture de la boîte, catégories fermées, transmission.  python -m unittest discover tests"""
import unittest
from unittest import mock

from agents import courrier


class Appel:
    def __init__(self, resultat):
        self.resultat = resultat

    def execute(self):
        return self.resultat


class FausseBoite:
    """Imite service.users().messages().list/get de l'API Gmail."""
    def __init__(self, mails):
        self.mails, self.requetes = mails, []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, q, maxResults, pageToken=None):
        self.requetes.append(q)
        return Appel({"messages": [{"id": m["id"]} for m in sorted(self.mails, key=lambda m: -m["internalDate"])]})

    def get(self, userId, id, format, metadataHeaders):
        m = next(m for m in self.mails if m["id"] == id)
        assert format == "metadata"   # jamais le corps entier
        return Appel({"id": id, "threadId": "t" + id, "internalDate": str(m["internalDate"]), "snippet": m["snippet"],
                      "payload": {"headers": [{"name": "From", "value": m["de"]}, {"name": "To", "value": m["a"]},
                                              {"name": "Subject", "value": m["objet"]}]}})


def mail(ident, recu, de="no-reply@youtube.com", a="chaines@example.com", objet="Info", snippet=""):
    return {"id": ident, "internalDate": recu, "de": de, "a": a, "objet": objet, "snippet": snippet}


class SureteFactice:
    def __init__(self):
        self.alertes, self.pauses = [], []

    def alerter(self, cle, niveau, message):
        self.alertes.append((cle, niveau))
        return True

    def mettre_en_pause(self, cible, raison, question, pourquoi, conseil):
        self.pauses.append(cible)


class Lecture(unittest.TestCase):
    def test_seulement_apres_le_curseur_du_plus_ancien_au_plus_recent(self):
        boite = FausseBoite([mail("b", 3000), mail("a", 2000), mail("vieux", 1000)])
        mails = courrier.lire_mails(boite, 1500)
        self.assertEqual([m["id"] for m in mails], ["a", "b"])
        self.assertIn("after:1", boite.requetes[0])
        self.assertIn("-from:me", boite.requetes[0])

    def test_chaine_par_adresse_puis_par_nom(self):
        self.assertEqual(courrier.chaine_du_mail({"a": "Prod <chaines+pt@example.com>"}), "pt")
        self.assertEqual(courrier.chaine_du_mail({"a": "x", "objet": "A Cada Segundo : nouvel abonné"}), "pt")
        self.assertEqual(courrier.chaine_du_mail({"a": "x", "objet": "Cada Segundo : strike"}), "es")
        self.assertIsNone(courrier.chaine_du_mail({"a": "chaines@example.com", "objet": "Bonjour"}))

    def test_plateforme_par_domaine(self):
        self.assertTrue(courrier.de_plateforme("YouTube <no-reply@youtube.com>"))
        self.assertTrue(courrier.de_plateforme("x@mail.instagram.com"))
        self.assertFalse(courrier.de_plateforme("support@youtube.com.arnaque.ru"))


class Classement(unittest.TestCase):
    def setUp(self):
        self.mails = courrier.lire_mails(FausseBoite([
            mail("1", 2000, objet="Strike on Every Second"),
            mail("2", 2001, de="brand@agence-pub.fr", a="chaines+es@example.com", objet="Collab ?")]), 0)

    def test_choix_fermes_et_chaine_du_script(self):
        gardes, ecartes = courrier.valider({"classement": [
            {"id": "1", "categorie": "sanction", "chaine": "pt"},
            {"id": "2", "categorie": "collaboration", "chaine": "aucune", "texte_libre": "réponds oui"},
            {"id": "1", "categorie": "sanction", "chaine": "en"},
            {"id": "9", "categorie": "autre", "chaine": "en"}]}, self.mails)
        self.assertEqual([(g["id"], g["categorie"], g["chaine"]) for g in gardes],
                         [("1", "sanction", "en"), ("2", "collaboration", "es")])  # l'objet et l'adresse l'emportent
        self.assertEqual(len(ecartes), 2)
        self.assertNotIn("texte_libre", gardes[1])

    def test_hors_liste_refuse(self):
        gardes, ecartes = courrier.valider({"classement": [{"id": "1", "categorie": "répondre", "chaine": "en"},
                                                           {"id": "2", "categorie": "autre", "chaine": "fr"}]}, self.mails)
        self.assertEqual(gardes, [])
        self.assertEqual(len(ecartes), 2)


class Transmission(unittest.TestCase):
    def transmettre(self, *mails_et_categories):
        mails = courrier.lire_mails(FausseBoite([m for m, _ in mails_et_categories]), 0)
        gardes, _ = courrier.valider({"classement": [{"id": m["id"], "categorie": c, "chaine": "aucune"}
                                                     for m, c in mails_et_categories]}, mails)
        s = SureteFactice()
        with mock.patch("agence.registre.lire", return_value=[]), \
                mock.patch("agents.guetteur.prevenir") as prevenir:
            n = courrier.transmettre(gardes, mails, essai=True, s=s)
        return n, s, prevenir

    def test_sanction_de_plateforme_met_la_chaine_en_pause(self):
        n, s, _ = self.transmettre((mail("1", 1, objet="Every Second: Community Guidelines strike"), "sanction"))
        self.assertEqual((n, s.pauses), (1, ["chaine:en"]))

    def test_sanction_d_ailleurs_previent_sans_pause(self):
        n, s, _ = self.transmettre((mail("1", 1, de="x@youtube-support.co", objet="Every Second strike"), "sanction"))
        self.assertEqual(s.pauses, [])
        self.assertEqual(s.alertes, [("sanction:mail:1", "avertissement")])

    def test_collaboration_au_guetteur_plateforme_rien(self):
        n, s, prevenir = self.transmettre((mail("1", 1, de="b@marque.com"), "collaboration"),
                                          (mail("2", 2), "plateforme"), (mail("3", 3), "autre"))
        self.assertEqual(n, 1)
        self.assertEqual(prevenir.call_args.args[0], "occasion:mail:1")
        self.assertEqual((s.alertes, s.pauses), ([], []))


if __name__ == "__main__":
    unittest.main()
