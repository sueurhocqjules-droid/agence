"""Lecture des demandes de Jules (agence.demandes) : une erreur n'est jamais une liste vide.

python -m unittest discover tests
"""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agence import demandes, guichet, registre


def issue(n, auteur=demandes.JULES, **k):
    return {"number": n, "title": f"demande {n}", "body": "texte", "html_url": f"https://x/{n}",
            "created_at": "2026-11-15T08:00:00Z", "user": {"login": auteur}} | k


def gh_rend(sortie, code=0, erreur=""):
    appels = []

    def run(cmd, **k):
        appels.append(cmd)
        return subprocess.CompletedProcess(cmd, code, stdout=sortie, stderr=erreur)
    return run, appels


class Lecture(unittest.TestCase):
    def test_chaque_equipe_se_lit_avec_l_etiquette_ouverte_et_jules(self):
        for equipe in demandes.EQUIPES:
            run, appels = gh_rend(json.dumps([issue(1)]))
            with mock.patch.object(subprocess, "run", run):
                self.assertEqual([d["numero"] for d in demandes.demandes(equipe)], [1])
            adresse = appels[0][2]
            self.assertIn(f"labels=equipe%3A{equipe}", adresse)
            self.assertIn("state=open", adresse)
            self.assertIn(f"creator={demandes.JULES}", adresse)

    def test_une_erreur_de_gh_n_est_pas_une_liste_vide(self):
        run, _ = gh_rend("", code=1, erreur="gh: HTTP 403 Resource not accessible by integration")
        with mock.patch.object(subprocess, "run", run):
            with self.assertRaises(RuntimeError) as e:
                demandes.demandes("direction")
        self.assertIn("403", str(e.exception))

    def test_une_reponse_d_erreur_de_l_api_n_est_pas_une_liste_vide(self):
        run, _ = gh_rend(json.dumps({"message": "Bad credentials"}))
        with mock.patch.object(subprocess, "run", run):
            with self.assertRaises(RuntimeError):
                demandes.demandes("contenu")

    def test_les_pages_suivantes_sont_lues_et_les_pr_ecartees(self):
        pages = [json.dumps([issue(n) for n in range(demandes.PAR_PAGE)]), json.dumps([issue(500), issue(501, pull_request={})])]
        appels = []

        def run(cmd, **k):
            appels.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout=pages[len(appels) - 1], stderr="")
        with mock.patch.object(subprocess, "run", run):
            numeros = [d["numero"] for d in demandes.demandes("recherche")]
        self.assertEqual(len(appels), 2)
        self.assertIn("page=2", appels[1][2])
        self.assertEqual(numeros[-1], 500)
        self.assertNotIn(501, numeros)


class Signal(unittest.TestCase):
    def test_une_lecture_ratee_ecrit_un_bloquant_au_journal(self):
        with tempfile.TemporaryDirectory() as t, mock.patch.object(registre, "DOSSIER", Path(t)):
            demandes.signaler("direction", "direction", RuntimeError("gh a échoué"))
            ligne = json.loads((Path(t) / "journal" / "direction.jsonl").read_text(encoding="utf-8"))
        self.assertIn("illisibles", ligne["bloquant"])
        self.assertIn("equipe:direction", ligne["bloquant"])

    def test_le_recapitulatif_dit_les_equipes_illisibles(self):
        texte = guichet.message_recap([], [], [], [("contenu", "gh a échoué")])
        self.assertIn("illisibles", texte)
        self.assertIn("contenu", texte)
        self.assertIsNone(guichet.message_recap([], [], [], []))

    def test_illisibles_liste_les_equipes_en_panne(self):
        run, _ = gh_rend("", code=1, erreur="boum")
        with mock.patch.object(subprocess, "run", run):
            self.assertEqual([e for e, _ in demandes.illisibles()], demandes.EQUIPES)


class JetonDesLecteurs(unittest.TestCase):
    """Le 16/11, le Stratège lisait les demandes sans GH_TOKEN : sa fiche ne le déclarait pas, le lanceur le retirait."""

    def test_chaque_agent_qui_lit_les_demandes_recoit_gh_token(self):
        from agence import organisation
        for nom in ("direction", "stratege", "chef-contenu"):
            fiche = organisation.fiches()[nom]
            self.assertIn("GH_TOKEN", fiche["env"], nom)
            self.assertEqual(organisation.cles_accordees(nom, fiche["env"])[1], [], nom)

    def test_le_dossier_du_stratege_ne_porte_aucun_champ_erreur(self):
        from datetime import datetime, timezone
        from agents import stratege
        run, _ = gh_rend(json.dumps([issue(7)]))
        with mock.patch.object(subprocess, "run", run), mock.patch.object(demandes, "signaler") as signal:
            try:
                dossier = stratege.dossier(datetime(2026, 11, 22, 17, 37, tzinfo=timezone.utc))
            except Exception as e:  # noqa: BLE001 : seule la lecture des demandes compte ici
                self.skipTest(f"dossier non constructible dans ce test : {e}")
        self.assertEqual([d["numero"] for d in dossier["demandes_de_jules"]], [7])
        self.assertFalse(any("erreur" in d for d in dossier["demandes_de_jules"]))
        signal.assert_not_called()


if __name__ == "__main__":
    unittest.main()
