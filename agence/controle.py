"""Contrôle d'une vidéo rendue avant sa programmation, par ffprobe et ffmpeg : 0 jeton.

Remplace le contrôle fait à la main pendant les nightworks (durée, son, images regardées).
Renvoie la liste des défauts : vide = la vidéo peut partir.
"""
import json
import re
import subprocess

DUREE_S = (20, 180)        # un Short d'Every Second dure ~70 s
FORMAT = (1080, 1920)
SON_MOYEN_MIN_DB = -40     # en dessous, la piste est muette
NOIR_MAX = 0.3             # part de la durée en écran noir


def _sonde(fichier):
    sortie = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height",
         "-of", "json", str(fichier)],
        capture_output=True, text=True, check=True,
    ).stdout
    return json.loads(sortie)


def _ffmpeg(fichier, filtres):
    return subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(fichier), *filtres, "-f", "null", "-"],
                          capture_output=True, text=True).stderr


def controler(fichier):
    """Renvoie (défauts, mesures) pour un mp4."""
    infos = _sonde(fichier)
    duree = float(infos["format"]["duration"])
    video = next((s for s in infos["streams"] if s["codec_type"] == "video"), None)
    a_du_son = any(s["codec_type"] == "audio" for s in infos["streams"])
    defauts = []
    if not DUREE_S[0] <= duree <= DUREE_S[1]:
        defauts.append(f"durée {duree:.1f} s")
    if not video or (video["width"], video["height"]) != FORMAT:
        defauts.append(f"format {video and (video['width'], video['height'])}")
    son = None
    if not a_du_son:
        defauts.append("pas de piste son")
    else:
        trouve = re.search(r"mean_volume: (-?[\d.]+) dB", _ffmpeg(fichier, ["-vn", "-af", "volumedetect"]))
        son = float(trouve.group(1)) if trouve else None
        if son is None or son < SON_MOYEN_MIN_DB:
            defauts.append(f"son muet ({son} dB)")
    noir = sum(float(d) for d in re.findall(r"black_duration:([\d.]+)", _ffmpeg(fichier, ["-an", "-vf", "blackdetect=d=0.5"])))
    if noir > NOIR_MAX * duree:
        defauts.append(f"écran noir {noir:.0f} s")
    return defauts, {"duree_s": round(duree, 2), "son_moyen_db": son, "noir_s": round(noir, 1)}
