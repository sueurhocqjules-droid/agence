"""Tests de l'agent flux : un artefact incomplet repart en rendu au lieu de bloquer le passage.  python -m unittest discover tests"""
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from agents import flux


def archive(*noms):
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w") as z:
        for nom in noms:
            z.writestr(nom, b"video")
    return tampon.getvalue()


class Telecharger(unittest.TestCase):
    def test_artefact_complet(self):
        with tempfile.TemporaryDirectory() as dossier, \
                mock.patch.object(flux, "gh", return_value=archive("volt-en.mp4", "volt-en-yt.mp4")):
            fichier = flux.telecharger({"archive_download_url": "x"}, dossier)
            self.assertEqual(fichier, Path(dossier) / "volt-en-yt.mp4")
            self.assertTrue(fichier.exists())

    def test_artefact_sans_version_youtube(self):
        """Cas du 11/11 : ffmpeg sans x264, la compression échoue, l'artefact n'a que le rendu brut."""
        with tempfile.TemporaryDirectory() as dossier, \
                mock.patch.object(flux, "gh", return_value=archive("volt-en.mp4")):
            self.assertIsNone(flux.telecharger({"archive_download_url": "x"}, dossier))


if __name__ == "__main__":
    unittest.main()
