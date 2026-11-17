"""Tests de la diffusion Instagram et Facebook de l'agent flux, sans appel réseau.  python -m unittest discover tests"""
import unittest
from datetime import datetime, timezone
from unittest import mock

from agence import meta
from agents import flux

MAINTENANT = datetime(2026, 11, 13, 12, tzinfo=timezone.utc)
SUJETS = ["volt", "coeur", "pluie"]


def sujet(s):
    return {"en": {"titre": f"titre {s}"}}, {"descriptions": {"en": f"desc {s}"}}


class Diffuser(unittest.TestCase):
    def lancer(self, publics, lignes=(), fichiers=None, cadence=None, ig_deja=(), fb_deja=(), echec=None):
        """Un passage de diffusion sur la seule chaîne en, avec des faux Meta, registre et rendus."""
        fichiers = fichiers if fichiers is not None else {s: (f"/tmp/{s}-en-yt.mp4", 70.0) for s in SUJETS}
        envoyes, notes = [], []

        def instagram(i, f, t, d):
            if echec:
                raise echec
            envoyes.append(("ig", t))
            return "m"
        with mock.patch.object(flux.youtube, "CHAINES", {"en": ("Every Second", "x")}), \
                mock.patch.object(flux, "lire_sujet", side_effect=sujet), \
                mock.patch.object(flux, "cadence_diffusion", return_value=cadence or {"instagram": 2, "facebook": 2}), \
                mock.patch.object(flux.registre, "lire", return_value=list(lignes)), \
                mock.patch.object(flux, "diffusion", side_effect=lambda *a, **k: notes.append(a)), \
                mock.patch.object(flux, "fichier_controle", side_effect=lambda nom, d: fichiers.get(nom.split("-")[0])), \
                mock.patch.object(flux, "heberger", side_effect=lambda f: f"https://raw/{f}"), \
                mock.patch.object(meta, "jeton", return_value="x"), \
                mock.patch.object(meta, "comptes_instagram", return_value={"en": "ig1"}), \
                mock.patch.object(meta, "jeton_page", return_value="page"), \
                mock.patch.object(meta, "titres_instagram", return_value=set(ig_deja)), \
                mock.patch.object(meta, "titres_facebook", return_value=set(fb_deja)), \
                mock.patch.object(meta, "publier_instagram", side_effect=instagram), \
                mock.patch.object(meta, "publier_facebook", side_effect=lambda p, c, f, t, d: envoyes.append(("fb", t)) or "v"):
            etats = {"en": (set(), set(), {f"titre {s}" for s in publics})}
            resultat = flux.diffuser(False, SUJETS, etats, [], "/tmp", MAINTENANT)
        return resultat, envoyes, notes

    def test_plus_ancien_dabord_et_cadence(self):
        (publiees, erreurs, a_rendre), envoyes, _ = self.lancer(publics=SUJETS, cadence={"instagram": 2, "facebook": 1})
        self.assertEqual(envoyes, [("ig", "titre volt"), ("ig", "titre coeur"), ("fb", "titre volt")])
        self.assertEqual((erreurs, a_rendre), ([], []))

    def test_seulement_les_videos_publiques_et_pas_deja_postees(self):
        _, envoyes, _ = self.lancer(publics=["coeur", "pluie"], ig_deja=["titre coeur"], fb_deja=["titre coeur", "titre pluie"])
        self.assertEqual(envoyes, [("ig", "titre pluie")])

    def test_cadence_deja_atteinte_aujourdhui(self):
        lignes = [{"date": "2026-11-13T08:00:00+00:00", "reseau": "instagram", "chaine": "en", "nom": f"x{i}-en",
                   "etat": "publie"} for i in range(2)]
        lignes.append({"date": "2026-11-12T08:00:00+00:00", "reseau": "facebook", "chaine": "en", "nom": "x-en",
                       "etat": "publie"})  # hier : ne compte pas
        _, envoyes, _ = self.lancer(publics=SUJETS, lignes=lignes)
        self.assertEqual(envoyes, [("fb", "titre volt"), ("fb", "titre coeur")])

    def test_rendu_expire_repart_en_rendu_dans_la_limite_du_jour(self):
        (_, _, a_rendre), envoyes, _ = self.lancer(publics=SUJETS, fichiers={})
        self.assertEqual(envoyes, [])
        self.assertEqual(a_rendre, ["volt-en", "coeur-en"])  # 2 places par jour : pas de rendu en trop

    def test_facebook_saute_plus_de_90_s(self):
        fichiers = {"volt": ("/tmp/volt-en-yt.mp4", 95.0), "coeur": ("/tmp/coeur-en-yt.mp4", 60.0)}
        _, envoyes, notes = self.lancer(publics=["volt", "coeur"], fichiers=fichiers, cadence={"instagram": 0, "facebook": 2})
        self.assertEqual(envoyes, [("fb", "titre coeur")])
        self.assertIn(("facebook", "en", "volt-en", "hors_format"), notes)

    def test_erreur_arrete_le_compte_et_se_signale(self):
        (_, erreurs, _), envoyes, notes = self.lancer(publics=SUJETS, cadence={"instagram": 2, "facebook": 0},
                                                      echec=meta.ErreurMeta("limite"))
        self.assertEqual(erreurs, ["instagram:volt-en"])  # un seul essai, pas de deuxième vidéo sur ce compte
        self.assertEqual(notes[0][:4], ("instagram", "en", "volt-en", "erreur"))

    def test_refus_instagram_ecrit_la_reponse_complete_en_bloquant(self):
        reponse = {"message": "Media upload has failed", "type": "OAuthException", "code": 2207026,
                   "error_subcode": 2207026, "fbtrace_id": "AbC123"}
        with mock.patch.object(flux.lancer, "noter_journal") as noter:
            self.lancer(publics=SUJETS, cadence={"instagram": 2, "facebook": 0},
                        echec=meta.ErreurMeta("POST ig1/media : Media upload has failed", 2207026, reponse))
        noter.assert_called_once()
        agent, entree = noter.call_args[0]
        self.assertEqual(agent, "chef-contenu")
        for morceau in ("volt-en", "2207026", "AbC123", "OAuthException"):
            self.assertIn(morceau, entree["bloquant"])

    def test_sans_jeton_rien_ne_part(self):
        with mock.patch.object(meta, "jeton", return_value=None):
            self.assertEqual(flux.diffuser(False, SUJETS, {}, [], "/tmp", MAINTENANT), ([], [], []))


class Legende(unittest.TestCase):
    def test_titre_en_premiere_ligne_et_limite(self):
        texte = meta.legende("Titre", "x" * 3000)
        self.assertTrue(texte.startswith("Titre\n\n"))
        self.assertEqual(len(texte), meta.LEGENDE_MAX)


class RefusInstagram(unittest.TestCase):
    def test_trois_refus_et_on_n_insiste_plus(self):
        refus = lambda n: [{"reseau": "instagram", "chaine": "en", "nom": "volt-en", "etat": "erreur"}] * n
        self.assertEqual(flux.essais_rates(refus(2) + [{"reseau": "facebook", "chaine": "en", "nom": "volt-en",
                                                        "etat": "erreur"}],
                                           "instagram", "volt-en"), 2)
        lancer = Diffuser("lancer").lancer
        _, envoyes, _ = lancer(publics=SUJETS, lignes=refus(2), cadence={"instagram": 1, "facebook": 0})
        self.assertEqual(envoyes, [("ig", "titre volt")])  # 3e essai
        _, envoyes, _ = lancer(publics=SUJETS, lignes=refus(3), cadence={"instagram": 1, "facebook": 0})
        self.assertEqual(envoyes, [("ig", "titre coeur")])  # volt abandonné, la suivante passe

    def test_refus_note_au_journal_comme_bloquant(self):
        with mock.patch.object(flux.registre, "ajouter"), mock.patch.object(flux.lancer, "noter_journal") as journal:
            flux.diffusion("instagram", "en", "volt-en", "erreur", note="code 2207003 : adresse illisible")
            flux.diffusion("facebook", "en", "volt-en", "erreur", note="autre")
        journal.assert_called_once()
        self.assertEqual(journal.call_args[0][0], "chef-contenu")
        self.assertIn("code 2207003", journal.call_args[0][1]["bloquant"])

    def test_conteneur_en_erreur_garde_le_code(self):
        reponses = iter([{"id": "c1"}, {"status_code": "ERROR", "status": "Error: failed with error code 2207003"}])
        with mock.patch.object(meta, "appel", side_effect=lambda *a, **k: next(reponses)):
            with self.assertRaises(meta.ErreurMeta) as e:
                meta.publier_instagram("ig1", "https://x/v.mp4", "t", "d")
        self.assertEqual(e.exception.code, 2207003)

    def test_publie_seulement_quand_le_conteneur_est_fini(self):
        appels = []
        reponses = iter([{"id": "c1"}, {"status_code": "IN_PROGRESS"}, {"status_code": "FINISHED"}, {"id": "m1"}])
        with mock.patch.object(meta, "appel", side_effect=lambda *a, **k: appels.append(a[1]) or next(reponses)), \
                mock.patch.object(meta.time, "sleep"):
            self.assertEqual(meta.publier_instagram("ig1", "https://x/v.mp4", "t", "d"), "m1")
        self.assertEqual(appels, ["ig1/media", "c1", "c1", "ig1/media_publish"])


if __name__ == "__main__":
    unittest.main()
