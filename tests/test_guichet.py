"""Guichet, autorisations des clés, contacts et ordre du mail du lundi.  python -m unittest discover tests"""
import base64
import json
import os
import re
import tempfile
import unittest
from datetime import datetime, timezone
from email import message_from_bytes
from pathlib import Path
from unittest import mock

from agence import contacts, guichet, lancer, organisation, protege
from agents import bilan

RACINE = Path(__file__).resolve().parent.parent
JULES, ROBOT = guichet.JULES, guichet.ROBOT


def issue(numero, titre, etiquettes=("guichet",), auteur=ROBOT, etat="open", texte="", pr=False, date="2026-11-14T08:00:00Z"):
    i = {"number": numero, "title": titre, "body": texte, "html_url": f"https://github.com/x/agence/issues/{numero}",
         "created_at": date, "closed_at": None if etat == "open" else date, "state": etat,
         "labels": [{"name": e} for e in etiquettes], "user": {"login": auteur}}
    return i | ({"pull_request": {}} if pr else {})


class FauxGitHub:
    """Remplace `gh` : rend les issues données, retient tout ce qui est écrit."""
    def __init__(self, issues=(), evenements=None):
        self.issues, self.evenements, self.appels = list(issues), evenements or {}, []

    def __call__(self, *args, entree=None):
        self.appels.append((args, entree))
        if args[:1] == ("api",) and "/events" in " ".join(args):
            numero = int(re.search(r"/issues/(\d+)/events", " ".join(args)).group(1))
            return "\n".join("\t".join(e) for e in self.evenements.get(numero, []))
        if args[:1] == ("api",):
            voulues = set(next(a for a in args if a.startswith("labels=")).split("=")[1].split(","))
            etat = next(a for a in args if a.startswith("state=")).split("=")[1]
            return json.dumps([i for i in self.issues if voulues <= {e["name"] for e in i["labels"]}
                               and (etat == "all" or i["state"] == etat)])
        if args[:2] == ("issue", "create"):
            return "https://github.com/x/agence/issues/77\n"
        return ""

    def ecrits(self, *debut):
        return [(a, e) for a, e in self.appels if a[:len(debut)] == debut]


DEMANDE = dict(quoi="Créer un compte Pexels", pourquoi="Images libres pour les vignettes", debloque="3 vignettes par jour",
               par="chef-contenu", lien="https://www.pexels.com/api/")


class Demande(unittest.TestCase):
    def setUp(self):
        self.decisions = []
        patch = mock.patch.object(guichet.registre, "decider", lambda *a, **k: self.decisions.append(a))
        patch.start()
        self.addCleanup(patch.stop)
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.etat = Path(dossier.name) / "guichet.json"
        for p in (mock.patch("builtins.print"), mock.patch.dict(os.environ, {"AGENCE_ESSAI": ""}),
                  mock.patch.object(guichet, "ETAT", self.etat)):
            p.start()
            self.addCleanup(p.stop)

    def test_format_fixe_dans_l_ordre(self):
        texte = guichet.corps("un compte", "pour X", "https://x", "Y", "0 €", "veilleur")
        positions = [texte.index(f"**{c} :**") for c in guichet.CHAMPS]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(guichet.CHAMPS, ("Quoi", "Pourquoi", "Lien", "Ce que ça débloque", "Coût"))

    def test_un_champ_vide_est_refuse_sauf_le_lien(self):
        for champ in ("quoi", "pourquoi", "debloque", "cout"):
            with self.subTest(champ=champ), self.assertRaises(ValueError):
                guichet.corps(**dict(quoi="a", pourquoi="b", lien="c", debloque="d", cout="e") | {champ: " "})
        self.assertIn("**Lien :** aucun", guichet.corps("a", "b", "", "d", "e"))

    def test_aucune_mention_possible(self):
        self.assertNotIn("@", guichet.corps("ping @sueurhocqjules-droid", "b", "c", "d", "e", "@x"))

    def test_une_demande_devient_une_issue_etiquetee_et_une_decision(self):
        gh = FauxGitHub()
        self.assertEqual(guichet.demander("Compte Pexels", gh=gh, **DEMANDE), (77, True))
        (args, entree), = gh.ecrits("issue", "create")
        self.assertEqual(args[args.index("--label") + 1], "guichet")
        self.assertIn("**Ce que ça débloque :** 3 vignettes par jour", entree)
        self.assertIn("**Coût :** 0 €", entree)
        self.assertEqual(len(self.decisions), 1)
        self.assertEqual([n["numero"] for n in json.loads(self.etat.read_text(encoding="utf-8"))["nouvelles"]], [77])

    def test_urgent_ajoute_l_etiquette(self):
        gh = FauxGitHub()
        guichet.demander("Compte Pexels", gh=gh, urgent=True, **DEMANDE)
        args = gh.ecrits("issue", "create")[0][0]
        self.assertEqual(args[args.index("--label") + 1], "guichet,urgent")

    def test_meme_titre_jamais_redemande_meme_ferme(self):
        for etat in ("open", "closed"):
            with self.subTest(etat=etat):
                gh = FauxGitHub([issue(5, "Compte Pexels", etat=etat)])
                self.assertEqual(guichet.demander("Compte Pexels", gh=gh, **DEMANDE), (5, False))
                self.assertFalse(gh.ecrits("issue", "create"))

    def test_en_essai_rien_n_est_ecrit(self):
        gh = FauxGitHub()
        with mock.patch.dict(os.environ, {"AGENCE_ESSAI": "1"}):
            self.assertEqual(guichet.demander("Compte Pexels", gh=gh, **DEMANDE), (None, False))
        self.assertFalse(gh.appels)

    def test_seules_les_demandes_de_l_agence_ou_de_jules_comptent(self):
        gh = FauxGitHub([issue(1, "a"), issue(2, "b", auteur=JULES), issue(3, "c", auteur="inconnu")])
        self.assertEqual([d["numero"] for d in guichet.ouvertes(gh)], [1, 2])

    def test_les_urgentes_d_abord(self):
        gh = FauxGitHub([issue(1, "a"), issue(2, "b", etiquettes=("guichet", "urgent"))])
        self.assertEqual([d["numero"] for d in guichet.ouvertes(gh)], [2, 1])

    def test_une_pr_protegee_arrive_au_guichet_au_meme_format(self):
        gh = FauxGitHub()
        guichet.signaler_pr(40, "fusionner", "fichier protégé", "la demande #12", "https://x/pull/40", gh=gh)
        self.assertEqual(gh.ecrits("pr", "edit")[0][0][-2:], ("--add-label", "guichet"))
        commentaire = gh.ecrits("pr", "comment")[0][1]
        for champ in guichet.CHAMPS:
            self.assertIn(f"**{champ} :**", commentaire)

    def test_une_pr_protegee_est_deposee_au_recapitulatif_une_seule_fois(self):
        gh = FauxGitHub()
        for _ in range(2):
            guichet.signaler_pr(40, "fusionner", "fichier protégé", "la demande #12", "https://x/pull/40", gh=gh,
                                demande="12")
        etat = guichet.lire_etat()
        self.assertEqual(list(etat["prs_a_dire"]), ["40"])
        message = etat["prs_a_dire"]["40"]
        for attendu in ("https://x/pull/40", "#12", "la demande #12", "ajouter l'étiquette accord-jules"):
            self.assertIn(attendu, message)
        envois = []
        matin = datetime(2026, 11, 14, 5, 17, tzinfo=timezone.utc)
        etat, envoyes = guichet.passage(matin, etat, [], [], [], envois.append)
        self.assertEqual(envoyes, ["récapitulatif"])
        self.assertIn("ajouter l'étiquette accord-jules", envois[0])
        self.assertEqual(etat["prs_a_dire"], {})
        guichet.ETAT.write_text(json.dumps(etat), encoding="utf-8")
        guichet.signaler_pr(40, "fusionner", "fichier protégé", "la demande #12", "https://x/pull/40", gh=gh)
        self.assertEqual(guichet.lire_etat()["prs_a_dire"], {})

    def test_le_message_attend_le_recapitulatif_s_il_n_est_pas_l_heure(self):
        etat = {"recap": "", "urgents": [], "signalees": [40], "prs_a_dire": {"40": "PR #40 en attente"}}
        envois = []
        etat, envoyes = guichet.passage(datetime(2026, 11, 13, 23, 17, tzinfo=timezone.utc), etat, [], [], [],
                                        envois.append)
        self.assertEqual((envoyes, envois), ([], []))
        self.assertEqual(list(etat["prs_a_dire"]), ["40"])


class Recap(unittest.TestCase):
    MATIN = datetime(2026, 11, 14, 5, 17, tzinfo=timezone.utc)    # 6h17 à Paris
    NUIT = datetime(2026, 11, 13, 23, 17, tzinfo=timezone.utc)    # 0h17 à Paris

    def passage(self, maintenant, etat, demandes=(), attente=(), cles=()):
        envois = []
        etat, envoyes = guichet.passage(maintenant, etat, list(demandes), list(attente), list(cles), envois.append)
        return etat, envoyes, envois

    def demande(self, numero, urgent=False):
        return {"numero": numero, "titre": f"demande {numero}", "lien": f"https://x/{numero}", "urgent": urgent,
                "texte": "- **Quoi :** x", "pr": False, "date": "2026-11-14T05:00:00Z"}

    def test_une_demande_ecrite_au_meme_reveil_est_dans_le_recapitulatif(self):
        # GitHub ne liste pas tout de suite une issue neuve : elle vient de l'état laissé par `demander`
        etat, envoyes, envois = self.passage(self.MATIN, {"nouvelles": [self.demande(13)]})
        self.assertEqual(envoyes, ["récapitulatif"])
        self.assertIn("#13 demande 13", envois[0])
        self.assertNotIn("nouvelles", etat)
        _, _, envois = self.passage(self.MATIN, {"nouvelles": [self.demande(13)]}, [self.demande(13)])
        self.assertEqual(envois[0].count("#13"), 1)      # déjà listée par GitHub : pas en double

    def test_un_recapitulatif_par_jour(self):
        etat, envoyes, envois = self.passage(self.MATIN, {}, [self.demande(1)])
        self.assertEqual(envoyes, ["récapitulatif"])
        self.assertIn("#1 demande 1", envois[0])
        etat, envoyes, envois = self.passage(self.MATIN.replace(hour=11), etat, [self.demande(1)])
        self.assertEqual((envoyes, envois), ([], []))
        _, envoyes, _ = self.passage(self.MATIN.replace(day=15), etat, [self.demande(1)])
        self.assertEqual(envoyes, ["récapitulatif"])

    def test_pas_de_message_la_nuit_ni_quand_rien_n_est_ouvert(self):
        self.assertEqual(self.passage(self.NUIT, {}, [self.demande(1)])[2], [])
        etat, envoyes, envois = self.passage(self.MATIN, {})
        self.assertEqual((envoyes, envois), ([], []))
        self.assertEqual(etat["recap"], "2026-11-14")

    def test_l_urgent_part_tout_de_suite_une_seule_fois(self):
        etat, envoyes, envois = self.passage(self.NUIT, {}, [self.demande(3, urgent=True)])
        self.assertEqual(envoyes, ["urgent #3"])
        self.assertIn("Demande urgente", envois[0])
        etat, envoyes, _ = self.passage(self.NUIT, etat, [self.demande(3, urgent=True)])
        self.assertEqual(envoyes, [])
        self.assertEqual(self.passage(self.NUIT, etat)[0]["urgents"], [])    # fermée : oubliée

    def test_le_recapitulatif_dit_les_contacts_et_les_cles_sans_accord(self):
        texte = guichet.message_recap([], [{"numero": 9, "titre": "Contact (Every Second) : x", "lien": "https://x/9"}],
                                      [("GMAIL_SEND_TOKEN", "contacts")])
        self.assertIn("1 message(s) à valider", texte)
        self.assertIn("GMAIL_SEND_TOKEN pour contacts", texte)
        self.assertIsNone(guichet.message_recap([], [], []))


class Autorisations(unittest.TestCase):
    TABLE = {"GMAIL_TOKEN": {"courrier"}, "GROQ_API_KEY": {"courrier", "critique"}}

    def test_une_cle_passe_si_declaree_et_accordee(self):
        self.assertEqual(organisation.cles_accordees("courrier", ["GMAIL_TOKEN", "GROQ_API_KEY"], self.TABLE),
                         ({"GMAIL_TOKEN", "GROQ_API_KEY"}, []))

    def test_se_declarer_une_cle_ne_suffit_pas(self):
        self.assertEqual(organisation.cles_accordees("critique", ["GMAIL_TOKEN", "GROQ_API_KEY"], self.TABLE),
                         ({"GROQ_API_KEY"}, ["GMAIL_TOKEN"]))

    def test_etre_autorise_sans_la_declarer_ne_donne_rien(self):
        self.assertEqual(organisation.cles_accordees("courrier", [], self.TABLE), (set(), []))

    def test_sans_fichier_aucune_cle(self):
        with mock.patch.object(organisation, "DOSSIER", RACINE / "tests" / "donnees"):
            self.assertEqual(organisation.autorisations(), {})

    def test_le_lanceur_ne_transmet_pas_une_cle_non_accordee(self):
        vus = {}

        class Proc:
            returncode, stdout = 0, []
            def __enter__(self): return self
            def __exit__(self, *a): return False

        def popen(commande, env=None, **k):
            vus.update(env)
            return Proc()

        postes = {"direction": {"id": "direction", "superieur": "jules"},
                  "x": {"id": "x", "superieur": "direction", "module": "m", "env": ["GMAIL_TOKEN", "GROQ_API_KEY"]}}
        with mock.patch.object(lancer.organisation, "fiches", lambda: postes), \
                mock.patch.object(lancer.organisation, "scripts", lambda: {}), \
                mock.patch.object(lancer.organisation, "autorisations", lambda: {"GROQ_API_KEY": {"x"}}), \
                mock.patch.object(lancer.registre, "lire", lambda table: []), \
                mock.patch.object(lancer, "noter_journal", lambda *a: None), \
                mock.patch.object(lancer.subprocess, "Popen", popen), mock.patch("builtins.print"), \
                mock.patch.dict(os.environ, {"GMAIL_TOKEN": "secret-mail", "GROQ_API_KEY": "secret-groq"}):
            self.assertEqual(lancer.lancer("x", []), 0)
        self.assertEqual(vus.get("GROQ_API_KEY"), "secret-groq")
        self.assertNotIn("GMAIL_TOKEN", vus)

    def test_le_fichier_ne_nomme_que_des_postes_et_scripts_qui_existent(self):
        connus = set(organisation.fiches()) | set(organisation.scripts())
        for cle, noms in organisation.autorisations().items():
            self.assertFalse(noms - connus, f"{cle} accordée à un nom inconnu : {noms - connus}")

    def test_le_fichier_est_protege(self):
        self.assertTrue(protege.raison("organisation/autorisations.toml", "modified"))
        self.assertTrue((RACINE / "organisation" / "autorisations.toml").exists())

    def test_le_droit_d_envoi_n_est_accorde_qu_au_script_des_contacts(self):
        self.assertLessEqual(organisation.autorisations().get(contacts.CLE, set()), {"contacts"})
        self.assertLessEqual(organisation.autorisations()["GMAIL_TOKEN"], {"courrier"})   # lire OU écrire, jamais les deux


MESSAGE = "Hello,\n\nThanks for reaching out. We would be glad to talk.\nHere is what we can offer."


class Contact(unittest.TestCase):
    def setUp(self):
        for p in (mock.patch.object(contacts.registre, "decider", lambda *a, **k: None), mock.patch("builtins.print"),
                  mock.patch.dict(os.environ, {"AGENCE_ESSAI": ""})):
            p.start()
            self.addCleanup(p.stop)

    def corps(self, **k):
        return contacts.corps(**dict(destinataires="marta@example.org", chaine="en", objet="Your proposal",
                                     contexte="Mail reçu le 12/11", message=MESSAGE, par="guetteur") | k)

    def test_aller_retour_du_format(self):
        lu = contacts.lire(self.corps())
        self.assertEqual(lu["destinataires"], ["marta@example.org"])
        self.assertEqual((lu["chaine"], lu["objet"]), ("en", "Your proposal"))
        self.assertTrue(lu["message"].startswith("Hello,"))

    def test_signe_par_l_equipe_de_la_chaine(self):
        self.assertTrue(contacts.lire(self.corps())["message"].endswith("The Every Second team"))
        self.assertTrue(contacts.lire(self.corps(chaine="pt"))["message"].endswith("A equipe A Cada Segundo"))
        self.assertEqual(contacts.signer(contacts.signer("Hi", "en"), "en").count("team"), 1)

    def test_jamais_au_nom_de_jules(self):
        for message in ("Hello, Jules here.", "Regards,\nJ. Hocq"):
            with self.subTest(message=message), self.assertRaises(ValueError):
                self.corps(message=message)

    def test_adresse_invalide_ou_lot_trop_gros_refuses(self):
        for destinataires in ("pas une adresse", "a@b.org; c@d.org", "", ", ".join(f"a{n}@b.org" for n in range(21))):
            with self.subTest(destinataires=destinataires), self.assertRaises(ValueError):
                self.corps(destinataires=destinataires)

    def test_un_lot_garde_tous_ses_destinataires(self):
        lu = contacts.lire(self.corps(destinataires=["a@b.org", "c@d.org"]))
        self.assertEqual(lu["destinataires"], ["a@b.org", "c@d.org"])

    def test_preparer_met_en_attente_sans_rien_envoyer(self):
        gh = FauxGitHub()
        self.assertEqual(contacts.preparer("marta@example.org", "en", "Your proposal", MESSAGE, "Mail reçu", "guetteur",
                                           gh=gh), 77)
        (args, entree), = gh.ecrits("issue", "create")
        self.assertEqual(args[args.index("--label") + 1], "contact")
        self.assertNotIn("valide", args)
        self.assertIn("<<<\nHello,", entree)

    def test_valide_ne_compte_que_pose_par_jules(self):
        self.assertTrue(contacts.valide_par_jules([("labeled", "valide", JULES)]))
        self.assertFalse(contacts.valide_par_jules([("labeled", "valide", ROBOT)]))
        self.assertFalse(contacts.valide_par_jules([("labeled", "valide", JULES), ("unlabeled", "valide", JULES)]))
        self.assertFalse(contacts.valide_par_jules([("labeled", "contact", JULES)]))


class Service:
    """Faux service Gmail : retient les mails envoyés, peut tomber en panne au n-ième."""
    def __init__(self, panne_au=None):
        self.envoyes, self.panne_au = [], panne_au

    def users(self): return self
    def messages(self): return self

    def send(self, userId, body):
        self.dernier = body
        return self

    def execute(self):
        if self.panne_au is not None and len(self.envoyes) + 1 == self.panne_au:
            raise RuntimeError("quota")
        self.envoyes.append(message_from_bytes(base64.urlsafe_b64decode(self.dernier["raw"])))


class Envoi(unittest.TestCase):
    def setUp(self):
        dossier = tempfile.TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        for p in (mock.patch.object(contacts.registre, "decider", lambda *a, **k: None), mock.patch("builtins.print"),
                  mock.patch.object(guichet, "ETAT", Path(dossier.name) / "guichet.json"),
                  mock.patch.object(guichet.registre, "decider", lambda *a, **k: None),
                  mock.patch.dict(os.environ, {"AGENCE_ESSAI": ""}),
                  mock.patch("builtins.open", mock.mock_open())):
            p.start()
            self.addCleanup(p.stop)

    def contact(self, numero, etiquettes=("contact", "valide"), destinataires="marta@example.org"):
        return issue(numero, f"Contact {numero}", etiquettes=etiquettes,
                     texte=contacts.corps(destinataires, "en", "Your proposal", "Mail reçu", MESSAGE, "guetteur"))

    def test_sans_droit_d_envoi_rien_ne_part_et_l_agence_le_demande_au_guichet(self):
        gh, service = FauxGitHub([self.contact(8)], {8: [("labeled", "valide", JULES)]}), Service()
        resume = contacts.passage(gh=gh, service=service, cle="")
        self.assertEqual(service.envoyes, [])
        (args, entree), = gh.ecrits("issue", "create")
        self.assertEqual(args[args.index("--label") + 1], "guichet")
        self.assertEqual(args[args.index("--title") + 1], contacts.TITRE_DEMANDE)
        self.assertIn("gmail.send", entree)
        self.assertIn("rien n'est parti", resume)
        self.assertFalse(gh.ecrits("issue", "close"))

    def test_la_demande_du_droit_d_envoi_n_est_faite_qu_une_fois(self):
        gh = FauxGitHub([issue(4, contacts.TITRE_DEMANDE)])
        self.assertIn("déjà faite", contacts.passage(gh=gh, service=Service(), cle=""))
        self.assertFalse(gh.ecrits("issue", "create"))

    def test_un_message_valide_par_jules_part_et_se_ferme(self):
        gh, service = FauxGitHub([self.contact(8)], {8: [("labeled", "valide", JULES)]}), Service()
        contacts.passage(gh=gh, service=service, cle="jeton")
        self.assertEqual([m["To"] for m in service.envoyes], ["marta@example.org"])
        self.assertEqual(service.envoyes[0]["Subject"], "Your proposal")
        self.assertIn("The Every Second team", service.envoyes[0].get_payload())
        self.assertTrue(gh.ecrits("issue", "close", "8"))

    def test_rien_ne_part_sans_validation_de_jules(self):
        cas = {"pas d'étiquette": (self.contact(8, etiquettes=("contact",)), []),
               "posée par le robot": (self.contact(8), [("labeled", "valide", ROBOT)]),
               "retirée": (self.contact(8), [("labeled", "valide", JULES), ("unlabeled", "valide", JULES)]),
               "issue d'un inconnu": (self.contact(8) | {"user": {"login": "inconnu"}}, [("labeled", "valide", JULES)])}
        for nom, (contact, evenements) in cas.items():
            with self.subTest(nom=nom):
                service = Service()
                contacts.passage(gh=FauxGitHub([contact], {8: evenements}), service=service, cle="jeton")
                self.assertEqual(service.envoyes, [])

    def test_un_lot_part_a_chacun_separement(self):
        gh = FauxGitHub([self.contact(8, destinataires="a@b.org, c@d.org")], {8: [("labeled", "valide", JULES)]})
        service = Service()
        contacts.passage(gh=gh, service=service, cle="jeton")
        self.assertEqual([m["To"] for m in service.envoyes], ["a@b.org", "c@d.org"])

    def test_un_envoi_interrompu_retire_la_validation(self):
        gh = FauxGitHub([self.contact(8, destinataires="a@b.org, c@d.org")], {8: [("labeled", "valide", JULES)]})
        service = Service(panne_au=2)
        with self.assertRaises(RuntimeError):
            contacts.passage(gh=gh, service=service, cle="jeton")
        self.assertEqual(len(service.envoyes), 1)
        self.assertEqual(gh.ecrits("issue", "edit")[0][0][-2:], ("--remove-label", "valide"))
        self.assertFalse(gh.ecrits("issue", "close"))

    def test_un_message_retouche_au_nom_de_jules_ne_part_pas(self):
        contact = self.contact(8)
        contact["body"] = contact["body"].replace("Hello,", "Hello, Jules here.")
        gh, service = FauxGitHub([contact], {8: [("labeled", "valide", JULES)]}), Service()
        with self.assertRaises(RuntimeError):
            contacts.passage(gh=gh, service=service, cle="jeton")
        self.assertEqual(service.envoyes, [])

    def test_le_jeton_d_envoi_n_a_que_le_droit_d_envoyer(self):
        self.assertEqual(contacts.SCOPE, "https://www.googleapis.com/auth/gmail.send")
        source = (RACINE / "agence" / "contacts.py").read_text(encoding="utf-8")
        self.assertNotIn("GMAIL_TOKEN\"", source)       # jamais le jeton de lecture du Courrier
        self.assertNotIn("gmail.readonly", source)


class MailDuLundi(unittest.TestCase):
    LUNDI = datetime(2026, 11, 16, 6, 37, tzinfo=timezone.utc)

    def page(self, **k):
        with mock.patch("builtins.print"):
            return bilan.page(self.LUNDI, **(dict(demandes=[], attente=[], fermees=[]) | k))

    def test_les_six_parties_dans_l_ordre_de_la_gouvernance(self):
        texte, _, _ = self.page()
        titres = re.findall(r"^## (.+)$", texte, re.MULTILINE)
        self.assertEqual(titres, list(bilan.ORDRE))
        self.assertEqual([t.split(". ", 1)[1] for t in bilan.ORDRE],
                         ["À valider", "Contacts en attente", "Demandes ouvertes", "Ce qui a été fait",
                          "Décisions jugées par le Critique", "Les 4 objectifs en chiffres"])

    def test_l_ordre_est_celui_ecrit_dans_la_mission(self):
        mission = (RACINE / "organisation" / "MISSION.md").read_text(encoding="utf-8")
        self.assertIn("à valider, contacts en attente, demandes ouvertes, ce qui a été fait (organisation comprise), "
                      "décisions jugées par le Critique, les 4 objectifs en chiffres", mission)

    def test_contacts_et_demandes_figurent_avec_leur_lien(self):
        demandes = [{"numero": 31, "titre": "Droit d'envoi Gmail", "lien": "https://x/31", "urgent": True, "pr": False,
                     "date": "2026-11-14T08:00:00Z"}]
        attente = [{"numero": 32, "titre": "Contact (Every Second) : Your proposal", "lien": "https://x/32",
                    "date": "2026-11-15T08:00:00Z"}]
        texte, resume, _ = self.page(demandes=demandes, attente=attente)
        partie = lambda n: texte.split(f"## {bilan.ORDRE[n]}")[1].split("\n## ")[0]
        self.assertIn("[#32](https://x/32)", partie(1))
        self.assertIn("**Urgent** : [#31](https://x/31)", partie(2))
        self.assertIn("1 contact(s) en attente", resume)
        self.assertIn("1 demande(s) au guichet", resume)

    def test_les_quatre_objectifs_ont_chacun_leur_chiffre(self):
        objectifs = self.page()[0].split(f"## {bilan.ORDRE[5]}")[1]
        for titre in ("### Argent", "### Économie", "### Autonomie", "### Apprentissage"):
            self.assertIn(titre, objectifs)

    def test_github_illisible_n_empeche_pas_le_bilan(self):
        with mock.patch.object(bilan.guichet, "ouvertes", side_effect=RuntimeError), \
                mock.patch.object(bilan.guichet, "toutes", side_effect=RuntimeError), \
                mock.patch.object(bilan.contacts, "en_attente", side_effect=RuntimeError), mock.patch("builtins.print"):
            texte, _, _ = bilan.page(self.LUNDI)
        self.assertEqual(texte.count("Liste illisible"), 2)

    def test_decisions_jugees_comptees_dans_la_periode(self):
        decisions = [{"decision": "baisser la cadence", "auteur": "direction",
                      "verdict": {"date": "2026-11-12T10:00:00+00:00", "verdict": "fausse", "commentaire": "vues en baisse"}},
                     {"decision": "vieille", "auteur": "direction",
                      "verdict": {"date": "2026-11-01T10:00:00+00:00", "verdict": "juste", "commentaire": ""}},
                     {"decision": "pas jugée", "auteur": "direction", "verdict": None}]
        debut, fin = bilan.periode(self.LUNDI)
        justes, fausses, indeterminees, lignes = bilan.jugees(decisions, debut, fin)
        self.assertEqual((justes, fausses, indeterminees), (0, 1, 0))
        self.assertIn("baisser la cadence", lignes[0])


class Reveil(unittest.TestCase):
    TEXTE = (RACINE / ".github" / "workflows" / "reveil.yml").read_text(encoding="utf-8")

    def test_le_guichet_passe_apres_les_contacts_et_avant_le_commit(self):
        ordre = [self.TEXTE.index(x) for x in ("agence.lancer guetteur", "agence.lancer contacts envoyer",
                                                "agence.lancer guichet recap", "name: Commiter le registre")]
        self.assertEqual(ordre, sorted(ordre))

    def test_le_jeton_d_envoi_ne_va_qu_a_l_etape_des_contacts(self):
        self.assertEqual(self.TEXTE.count("secrets.GMAIL_SEND_TOKEN"), 1)
        etape = self.TEXTE.split("name: Contacts (messages validés)")[1].split("- name:")[0]
        self.assertIn("secrets.GMAIL_SEND_TOKEN", etape)
        self.assertNotIn("secrets.GMAIL_TOKEN", etape)

    def test_guichet_et_contacts_sont_des_scripts_avec_un_proprietaire(self):
        scripts = organisation.scripts()
        for nom, module in (("guichet", "agence.guichet"), ("contacts", "agence.contacts")):
            self.assertEqual(scripts[nom]["module"], module)
            self.assertIn(nom, organisation.fiches()[scripts[nom]["proprietaire"]]["scripts"])


if __name__ == "__main__":
    unittest.main()
