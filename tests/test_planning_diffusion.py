"""Tests du relais de diffusion planifiée (agents/diffusion.py), sans appel réseau.
python -m unittest discover tests"""
import unittest
from datetime import datetime, timezone

from agents import diffusion

MAINTENANT = datetime(2026, 11, 23, 17, 5, tzinfo=timezone.utc)


def ligne(nom, heure="2026-11-23T17:00:00+00:00", reseau="instagram", langue="en"):
    return {"apres_utc": heure, "reseau": reseau, "langue": langue, "nom": nom, "titre": f"titre {nom}",
            "texte": "texte", "adresse": f"https://exemple/{nom}.mp4"}


def registre(nom, etat, reseau="instagram"):
    return {"date": "2026-11-23T09:31:00+00:00", "reseau": reseau, "chaine": "en", "nom": nom, "etat": etat,
            "media_id": "", "note": ""}


class Dues(unittest.TestCase):
    def test_heure_pas_encore_venue(self):
        groupes = diffusion.dues([ligne("a"), ligne("b", heure="2026-11-23T23:00:00+00:00")], [], MAINTENANT)
        self.assertEqual([p["nom"] for p in groupes[("instagram", "en")]], ["a"])

    def test_deja_publiee_sur_ce_reseau_seulement(self):
        planning = [ligne("a"), ligne("a", reseau="tiktok")]
        groupes = diffusion.dues(planning, [registre("a", "publie")], MAINTENANT)
        self.assertNotIn(("instagram", "en"), groupes)
        self.assertEqual([p["nom"] for p in groupes[("tiktok", "en")]], ["a"])

    def test_plafond_par_compte_plus_ancienne_d_abord(self):
        planning = [ligne("c"), ligne("b", heure="2026-11-23T09:30:00+00:00"), ligne("a", heure="2026-11-22T23:00:00+00:00"),
                    ligne("d", langue="pt")]
        groupes = diffusion.dues(planning, [], MAINTENANT)
        self.assertEqual([p["nom"] for p in groupes[("instagram", "en")]], ["a", "b"])
        self.assertEqual([p["nom"] for p in groupes[("instagram", "pt")]], ["d"])

    def test_abandon_apres_trois_refus(self):
        refus = [registre("a", "erreur")] * diffusion.ESSAIS_MAX
        self.assertEqual(diffusion.dues([ligne("a")], refus, MAINTENANT), {})
        self.assertIn(("instagram", "en"), diffusion.dues([ligne("a")], refus[:-1], MAINTENANT))


if __name__ == "__main__":
    unittest.main()
