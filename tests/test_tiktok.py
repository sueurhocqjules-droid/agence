"""Tests de la diffusion TikTok par Buffer (agence/buffer.py, agents/flux.py), sans appel réseau.
python -m unittest discover tests"""
import unittest
from datetime import datetime, timezone
from unittest import mock

from agence import buffer
from agents import flux

MAINTENANT = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
SUJETS = ["volt", "coeur", "pluie"]
CHAINES = {"en": ("Every Second", "x"), "es": ("Cada Segundo", "y")}


def sujet(s):
    return ({"en": {"titre": f"titre {s}"}, "es": {"titre": f"título {s}"}},
            {"descriptions": {"en": f"desc {s}", "es": f"desc es {s}"}})


def post(texte, statut="sent", i="p"):
    return {"id": i, "text": texte, "status": statut}


class Diffuser(unittest.TestCase):
    def lancer(self, publics, lignes=(), fichiers=None, par_jour=2, chaines=None, deja=(), echec=None, relu="sent",
               pauses=(), essai=False):
        """Un passage TikTok sur les chaînes en et es, avec un faux Buffer, registre et rendus."""
        fichiers = fichiers if fichiers is not None else {s: (f"/tmp/{s}-yt.mp4", 70.0) for s in SUJETS}
        chaines = {"en": "c-en"} if chaines is None else chaines
        envoyes, notes, heberges = [], [], []

        def publier(chaine, adresse, texte, ia=False):
            if echec:
                raise echec
            envoyes.append((chaine, adresse, texte.split("\n")[0], ia))
            return f"post{len(envoyes)}"

        def confirmer(org, crees):
            return {i: {"id": i, "status": relu, "externalLink": "https://tiktok/x",
                        "error": {"message": "refusé"} if relu == "error" else None} for i in crees}

        def heberger_tous(liste):
            heberges.append(list(liste))
            return {f: f"https://raw/{f}" for f in liste}
        with mock.patch.object(flux.youtube, "CHAINES", CHAINES), \
                mock.patch.object(flux, "lire_sujet", side_effect=sujet), \
                mock.patch.object(flux, "cadence_diffusion", return_value={"tiktok": par_jour}), \
                mock.patch.object(flux.registre, "lire", return_value=list(lignes)), \
                mock.patch.object(flux, "diffusion", side_effect=lambda *a, **k: notes.append(a)), \
                mock.patch.object(flux, "fichier_controle", side_effect=lambda nom, d: fichiers.get(nom.split("-")[0])), \
                mock.patch.object(flux, "heberger_tous", side_effect=heberger_tous), \
                mock.patch.object(buffer, "jeton", return_value="x"), \
                mock.patch.object(buffer, "organisation", return_value="org"), \
                mock.patch.object(buffer, "chaines_tiktok", return_value=chaines), \
                mock.patch.object(buffer, "posts", return_value=list(deja)), \
                mock.patch.object(buffer, "publier", side_effect=publier), \
                mock.patch.object(buffer, "confirmer", side_effect=confirmer):
            etats = {l: (set(), set(), {f"titre {s}" for s in publics} | {f"título {s}" for s in publics})
                     for l in CHAINES}
            resultat = flux.diffuser_tiktok(essai, SUJETS, etats, list(pauses), "/tmp", MAINTENANT)
        return resultat, envoyes, notes, heberges

    def test_plus_ancien_dabord_cadence_et_un_seul_hebergement(self):
        (publiees, erreurs, a_rendre), envoyes, notes, heberges = self.lancer(publics=SUJETS)
        self.assertEqual([e[2] for e in envoyes], ["titre volt", "titre coeur"])
        self.assertEqual(publiees, ["tiktok:volt-en", "tiktok:coeur-en"])
        self.assertEqual((erreurs, a_rendre), ([], []))
        self.assertEqual(heberges, [["/tmp/volt-yt.mp4", "/tmp/coeur-yt.mp4"]])  # un seul commit pour le passage
        self.assertEqual(envoyes[0][1], "https://raw//tmp/volt-yt.mp4")
        self.assertIn(("tiktok", "en", "volt-en", "publie", "post1"), notes)

    def test_chaine_absente_de_buffer_sautee_sans_erreur(self):
        (publiees, erreurs, _), envoyes, _, _ = self.lancer(publics=SUJETS, par_jour=1)
        self.assertEqual([e[0] for e in envoyes], ["c-en"])  # es pas branché : sauté
        self.assertEqual(erreurs, [])

    def test_deja_sur_tiktok_ou_post_en_erreur(self):
        deja = [post("titre volt\n\ndesc"), post("titre coeur", statut="error")]
        _, envoyes, _, _ = self.lancer(publics=SUJETS, deja=deja)
        self.assertEqual([e[2] for e in envoyes], ["titre coeur", "titre pluie"])  # un post en erreur n'a rien publié

    def test_cadence_du_jour_deja_atteinte(self):
        lignes = [{"date": "2026-11-14T08:00:00+00:00", "reseau": "tiktok", "chaine": "en", "nom": f"x{i}-en",
                   "etat": "publie"} for i in range(2)]
        _, envoyes, _, heberges = self.lancer(publics=SUJETS, lignes=lignes)
        self.assertEqual((envoyes, heberges), ([], []))

    def test_file_buffer_jamais_au_dela_de_10(self):
        deja = [post(f"autre {i}", statut="scheduled", i=str(i)) for i in range(9)]
        _, envoyes, _, _ = self.lancer(publics=SUJETS, deja=deja)
        self.assertEqual(len(envoyes), 1)
        _, envoyes, _, _ = self.lancer(publics=SUJETS, deja=deja + [post("autre 9", statut="sending")])
        self.assertEqual(envoyes, [])

    def test_pause_tiktok_respectee(self):
        pause = {"cible": "reseau:tiktok", "par": "surete", "raison": "test", "jusqu": "", "levee": ""}
        with mock.patch.object(flux.lancer, "pause_active", side_effect=lambda cibles, p: pause if "reseau:tiktok" in cibles else None):
            _, envoyes, _, _ = self.lancer(publics=SUJETS, pauses=[pause])
        self.assertEqual(envoyes, [])

    def test_hors_format_et_rendu_expire(self):
        fichiers = {"volt": ("/tmp/volt-yt.mp4", 2.0), "pluie": ("/tmp/pluie-yt.mp4", 50.0)}  # coeur : rendu expiré
        (_, _, a_rendre), envoyes, notes, _ = self.lancer(publics=SUJETS, fichiers=fichiers, par_jour=3)
        self.assertIn(("tiktok", "en", "volt-en", "hors_format"), notes)
        self.assertEqual(a_rendre, ["coeur-en"])
        self.assertEqual([e[2] for e in envoyes], ["titre pluie"])

    def test_refus_de_buffer_arrete_le_compte_et_se_signale(self):
        (publiees, erreurs, _), envoyes, notes, _ = self.lancer(publics=SUJETS, echec=buffer.ErreurBuffer("file pleine"))
        self.assertEqual((publiees, erreurs), ([], ["tiktok:volt-en"]))  # un seul essai sur ce compte
        self.assertEqual(notes[0][:4], ("tiktok", "en", "volt-en", "erreur"))

    def test_post_en_erreur_a_la_relecture(self):
        (publiees, erreurs, _), _, notes, _ = self.lancer(publics=["volt"], relu="error")
        self.assertEqual((publiees, erreurs), ([], ["tiktok:volt-en"]))
        self.assertEqual(notes[0][3], "erreur")

    def test_essai_ne_publie_rien(self):
        _, envoyes, notes, heberges = self.lancer(publics=SUJETS, essai=True)
        self.assertEqual((envoyes, notes, heberges), ([], [], []))

    def test_sans_cle_ou_cadence_nulle_rien_ne_part(self):
        with mock.patch.object(flux, "cadence_diffusion", return_value={"tiktok": 2}), \
                mock.patch.object(buffer, "jeton", return_value=None):
            self.assertEqual(flux.diffuser_tiktok(False, SUJETS, {}, [], "/tmp", MAINTENANT), ([], [], []))
        with mock.patch.object(flux, "cadence_diffusion", return_value={"instagram": 2}):
            self.assertEqual(flux.diffuser_tiktok(False, SUJETS, {}, [], "/tmp", MAINTENANT), ([], [], []))

    def test_buffer_injoignable_se_signale(self):
        with mock.patch.object(flux, "cadence_diffusion", return_value={"tiktok": 2}), \
                mock.patch.object(flux.registre, "lire", return_value=[]), \
                mock.patch.object(flux, "diffusion"), \
                mock.patch.object(buffer, "jeton", return_value="x"), \
                mock.patch.object(buffer, "organisation", side_effect=buffer.ErreurBuffer("HTTP 401")):
            self.assertEqual(flux.diffuser_tiktok(False, SUJETS, {}, [], "/tmp", MAINTENANT), ([], ["tiktok:buffer"], []))


class Api(unittest.TestCase):
    def test_chaines_lues_dans_buffer_par_nom(self):
        reponse = {"channels": [
            {"id": "a", "name": "everysecondlab", "service": "tiktok", "isDisconnected": False},
            {"id": "b", "name": "acadasegundolab", "service": "tiktok", "isDisconnected": True},   # débranchée
            {"id": "c", "name": "cadasegundolab", "service": "instagram", "isDisconnected": False},  # pas TikTok
            {"id": "d", "name": "inconnu", "service": "tiktok", "isDisconnected": False}]}
        with mock.patch.object(buffer, "appel", return_value=reponse):
            self.assertEqual(buffer.chaines_tiktok("org"), {"en": "a"})

    def test_publier_forme_du_post(self):
        with mock.patch.object(buffer, "appel", return_value={"createPost": {"post": {"id": "p1"}}}) as appel:
            self.assertEqual(buffer.publier("c", "https://v.mp4", "texte", ia=False), "p1")
        entree = appel.call_args[0][1]["input"]
        self.assertEqual((entree["schedulingType"], entree["mode"]), ("automatic", "shareNow"))
        self.assertEqual(entree["assets"][0]["video"]["url"], "https://v.mp4")
        self.assertIs(entree["metadata"]["tiktok"]["isAiGenerated"], False)

    def test_publier_refus_de_buffer(self):
        with mock.patch.object(buffer, "appel", return_value={"createPost": {"message": "Queue full"}}):
            with self.assertRaisesRegex(buffer.ErreurBuffer, "Queue full"):
                buffer.publier("c", "u", "t")

    def test_posts_pages(self):
        pages = [{"posts": {"edges": [{"node": {"id": "1"}}], "pageInfo": {"hasNextPage": True, "endCursor": "k"}}},
                 {"posts": {"edges": [{"node": {"id": "2"}}], "pageInfo": {"hasNextPage": False}}}]
        with mock.patch.object(buffer, "appel", side_effect=pages) as appel:
            self.assertEqual([p["id"] for p in buffer.posts("org", "c")], ["1", "2"])
        self.assertIn('after: "k"', appel.call_args_list[1][0][0])

    def test_confirmer_attend_la_fin(self):
        pages = [[{"id": "p1", "status": "sending"}], [{"id": "p1", "status": "sent"}]]
        with mock.patch.object(buffer, "posts", side_effect=pages), mock.patch.object(buffer.time, "sleep") as dort:
            self.assertEqual(buffer.statut(buffer.confirmer("org", {"p1": "c"})["p1"]), "sent")
        self.assertEqual(dort.call_count, 1)

    def test_cle_jamais_dans_l_erreur(self):
        erreur = buffer.urllib.error.HTTPError(buffer.API, 401, "Unauthorized", {}, None)
        with mock.patch.dict(buffer.os.environ, {"BUFFER_API_KEY": "secret-123"}), \
                mock.patch.object(buffer.urllib.request, "urlopen", side_effect=erreur):
            with self.assertRaises(buffer.ErreurBuffer) as e:
                buffer.appel("query { x }")
        self.assertNotIn("secret-123", str(e.exception))


class Legende(unittest.TestCase):
    def test_titre_puis_description(self):
        self.assertEqual(buffer.legende("Titre", "Desc"), "Titre\n\nDesc")

    def test_cinq_hashtags_au_plus(self):
        texte = buffer.legende("Titre #a", "Desc #b #c #d #e #f #g")
        self.assertEqual(texte.count("#"), 5)
        self.assertTrue(texte.endswith("#e"))

    def test_longueur_max(self):
        self.assertEqual(len(buffer.legende("T", "x" * 3000)), buffer.LEGENDE_MAX)


if __name__ == "__main__":
    unittest.main()
