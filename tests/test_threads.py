"""Tests de la diffusion Threads (agence/threads.py, agents/flux.py), sans appel réseau.
python -m unittest discover tests"""
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from agence import threads
from agents import flux

MAINTENANT = datetime(2026, 11, 15, 12, tzinfo=timezone.utc)
SUJETS = ["volt", "coeur", "pluie"]


def sujet(s):
    return {"en": {"titre": f"titre {s}"}}, {"descriptions": {"en": f"desc {s}"}}


def compte(jours=1, expire=55):
    return {"id": "u1", "nom": "everysecondlab", "jeton": "secret-123",
            "obtenu": (MAINTENANT - timedelta(days=jours)).isoformat(),
            "expire": (MAINTENANT + timedelta(days=expire)).isoformat()}


class Legende(unittest.TestCase):
    def test_un_seul_sujet_garde(self):
        self.assertEqual(threads.legende("Titre", "texte #un #deux\n#trois"), "Titre\n\ntexte #un")

    def test_coupee_a_500_octets_sur_un_blanc(self):
        texte = threads.legende("Título", "é " * 400)
        self.assertLessEqual(len(texte.encode()), threads.TEXTE_MAX_OCTETS)
        self.assertTrue(texte.startswith("Título\n\n"))
        self.assertFalse(texte.endswith(" "))


class Branchement(unittest.TestCase):
    def test_code_depuis_adresse_ou_seul(self):
        self.assertEqual(threads.code_de(f"{threads.REDIRECTION}?code=AbC123&state=es#_"), "AbC123")
        self.assertEqual(threads.code_de(" AbC123#_ "), "AbC123")

    def test_lien_porte_appli_redirection_et_langue(self):
        lien = threads.lien("es")
        self.assertIn(f"client_id={threads.APP_ID}", lien)
        self.assertIn("state=es", lien)
        self.assertIn("threads_content_publish", lien)

    def test_mauvais_compte_refuse_et_rien_ecrit(self):
        reponses = iter([{"access_token": "court", "user_id": "9"}, {"access_token": "long", "expires_in": 5183944},
                         {"id": "9", "username": "acadasegundolab"}])
        with mock.patch.object(threads, "secret", return_value="app"), \
                mock.patch.object(threads, "appel", side_effect=lambda *a, **k: next(reponses)), \
                mock.patch.object(threads, "ecrire") as ecrire:
            with self.assertRaises(threads.ErreurThreads):
                threads.brancher("es", "code")
        ecrire.assert_not_called()

    def test_jetons_chiffres_relus(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.object(threads, "FICHIER", Path(d) / "threads.enc"), \
                mock.patch.dict(threads.os.environ, {"THREADS_CLE": "cle-de-test"}):
            threads.ecrire({"en": compte()})
            self.assertNotIn(b"secret-123", threads.FICHIER.read_bytes())
            self.assertEqual(threads.lire(), {"en": compte()})
            with mock.patch.dict(threads.os.environ, {"THREADS_CLE": "autre"}), \
                    self.assertRaises(threads.ErreurThreads):
                threads.lire()


class Renouveler(unittest.TestCase):
    def test_jeton_recent_garde(self):
        with mock.patch.object(threads, "appel") as appel:
            comptes, problemes = threads.renouveler({"en": compte(jours=2)}, MAINTENANT)
        appel.assert_not_called()
        self.assertEqual((comptes, problemes), ({"en": compte(jours=2)}, []))

    def test_jeton_ancien_renouvele(self):
        with mock.patch.object(threads, "appel", return_value={"access_token": "neuf", "expires_in": 5184000}):
            comptes, problemes = threads.renouveler({"en": compte(jours=8)}, MAINTENANT)
        self.assertEqual(comptes["en"]["jeton"], "neuf")
        self.assertEqual(comptes["en"]["obtenu"], MAINTENANT.isoformat(timespec="seconds"))
        self.assertEqual(problemes, [])

    def test_refus_et_fin_proche_signales(self):
        with mock.patch.object(threads, "appel", side_effect=threads.ErreurThreads("GET refresh : expiré")):
            comptes, problemes = threads.renouveler({"en": compte(jours=50, expire=5)}, MAINTENANT)
        self.assertEqual(comptes["en"]["jeton"], "secret-123")
        self.assertEqual(len(problemes), 2)
        self.assertTrue(all(p.startswith("en : ") for p in problemes))


class Diffuser(unittest.TestCase):
    def lancer(self, publics, comptes=None, lignes=(), par_jour=2, deja=(), echec=None, fichiers=None, essai=False,
               renouvellement=None):
        fichiers = fichiers if fichiers is not None else {s: (f"/tmp/{s}-en-yt.mp4", 70.0) for s in SUJETS}
        comptes = {"en": compte()} if comptes is None else comptes
        envoyes, notes, ecrits = [], [], []

        def publier(c, adresse, titre, description):
            if echec:
                raise echec
            envoyes.append(titre)
            return "t1"
        with mock.patch.object(flux.youtube, "CHAINES", {"en": ("Every Second", "x")}), \
                mock.patch.object(flux, "lire_sujet", side_effect=sujet), \
                mock.patch.object(flux, "cadence_diffusion", return_value={"threads": par_jour}), \
                mock.patch.object(flux.registre, "lire", return_value=list(lignes)), \
                mock.patch.object(flux, "diffusion", side_effect=lambda *a, **k: notes.append((a, k))), \
                mock.patch.object(flux, "fichier_controle", side_effect=lambda nom, d: fichiers.get(nom.split("-")[0])), \
                mock.patch.object(flux, "heberger", side_effect=lambda f: f"https://raw/{f}"), \
                mock.patch.object(threads, "lire", return_value=comptes), \
                mock.patch.object(threads, "renouveler", return_value=renouvellement or (comptes, [])), \
                mock.patch.object(threads, "ecrire", side_effect=ecrits.append), \
                mock.patch.object(threads, "titres", return_value=set(deja)), \
                mock.patch.object(threads, "publier", side_effect=publier):
            etats = {"en": (None, None, {f"titre {s}" for s in publics})}
            resultat = flux.diffuser_threads(essai, SUJETS, etats, [], "/tmp", MAINTENANT)
        return resultat, envoyes, notes, ecrits

    def test_plus_ancienne_d_abord_a_la_cadence(self):
        (publiees, erreurs, a_rendre), envoyes, notes, _ = self.lancer(SUJETS)
        self.assertEqual(envoyes, ["titre volt", "titre coeur"])
        self.assertEqual(publiees, ["threads:volt-en", "threads:coeur-en"])
        self.assertEqual([a[0][3] for a in notes], ["publie", "publie"])

    def test_deja_publiee_et_quota_du_jour(self):
        lignes = [{"date": MAINTENANT.isoformat(), "reseau": "threads", "chaine": "en", "nom": "x", "etat": "publie"}]
        _, envoyes, _, _ = self.lancer(SUJETS, lignes=lignes, deja={"titre volt"})
        self.assertEqual(envoyes, ["titre coeur"])

    def test_compte_pas_branche_saute(self):
        resultat, envoyes, notes, _ = self.lancer(SUJETS, comptes={"es": compte()})
        self.assertEqual((resultat, envoyes, notes), (([], [], []), [], []))

    def test_aucun_compte_rien(self):
        resultat, envoyes, _, _ = self.lancer(SUJETS, comptes={})
        self.assertEqual((resultat, envoyes), (([], [], []), []))

    def test_trop_longue_hors_format(self):
        fichiers = {"volt": ("/tmp/v.mp4", 301.0), "coeur": ("/tmp/c.mp4", 60.0), "pluie": ("/tmp/p.mp4", 60.0)}
        _, envoyes, notes, _ = self.lancer(SUJETS, fichiers=fichiers)
        self.assertEqual(envoyes, ["titre coeur", "titre pluie"])
        self.assertEqual(notes[0][0][3], "hors_format")

    def test_rendu_manquant_a_rendre(self):
        (_, _, a_rendre), envoyes, _, _ = self.lancer(SUJETS, fichiers={"coeur": ("/tmp/c.mp4", 60.0)})
        self.assertEqual((a_rendre, envoyes), (["volt-en"], ["titre coeur"]))

    def test_erreur_arrete_le_compte(self):
        (publiees, erreurs, _), envoyes, notes, _ = self.lancer(SUJETS, echec=threads.ErreurThreads("limite"))
        self.assertEqual((publiees, erreurs), ([], ["threads:volt-en"]))
        self.assertEqual(len(notes), 1)

    def test_essai_n_envoie_ni_ne_renouvelle(self):
        _, envoyes, notes, ecrits = self.lancer(SUJETS, essai=True, renouvellement=({"en": {}}, ["en : x"]))
        self.assertEqual((envoyes, notes, ecrits), ([], [], []))

    def test_jetons_renouveles_ecrits_et_problemes_notes_meme_a_cadence_zero(self):
        neufs = {"en": {**compte(), "jeton": "neuf"}}
        (_, erreurs, _), envoyes, notes, ecrits = self.lancer(SUJETS, par_jour=0,
                                                               renouvellement=(neufs, ["en : jeton perdu dans 3 jours"]))
        self.assertEqual(ecrits, [neufs])
        self.assertEqual(erreurs, ["threads:en"])
        self.assertEqual(notes[0][0][:4], ("threads", "en", "", "erreur"))
        self.assertEqual(envoyes, [])

    def test_cle_absente_signalee(self):
        with mock.patch.object(threads, "lire", side_effect=threads.ErreurThreads("clé THREADS_CLE absente")), \
                mock.patch.object(flux, "diffusion") as diffusion:
            resultat = flux.diffuser_threads(False, SUJETS, {}, [], "/tmp", MAINTENANT)
        self.assertEqual(resultat, ([], ["threads:jetons"], []))
        diffusion.assert_called_once()


if __name__ == "__main__":
    unittest.main()
