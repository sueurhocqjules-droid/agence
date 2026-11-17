"""L'équipe du Pilote : des scripts qu'il écrit lui-même (dossier equipe/) et que le réveil fait tourner sans Claude,
4 fois par jour, dans l'ordre de organisation/equipe.toml.

    python -m agence.equipe

organisation/equipe.toml (à lui) :
    [[membre]]
    nom = "veille"                 # lettres, chiffres, tirets
    module = "equipe.veille"       # toujours dans equipe/
    minutes = 5                    # coupé au-delà (au plus 10)
    args = ["--langue", "en"]      # facultatif

Chaque membre écrit ses résultats dans registre/equipe/<nom>/, commité par le réveil et lu par le Pilote à la
séance suivante. Il ne reçoit que les clés des modèles gratuits et la clé YouTube en lecture (données publiques) :
son code est écrit par le Pilote, gardé seulement après les tests et une relecture par un modèle qui n'est pas Claude.
Les clés qui publient ou envoient restent aux scripts de organisation/scripts.toml.
"""
import json
import os
import re
import subprocess
import sys
import tomllib
from datetime import datetime, timezone

from agence import lancer, organisation, registre

CLES = {"GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "YOUTUBE_API_KEY"}
NOM = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
MODULE = re.compile(r"^equipe(\.[a-z_][a-z0-9_]*)+$")
MINUTES_MAX = 10
TOTAL_MAX_S = 20 * 60         # le réveil a d'autres étapes après l'équipe
MEMBRES_MAX = 12


def membres(texte):
    """Membres valides de equipe.toml, et les erreurs de ceux qui sont écartés."""
    try:
        donnees = tomllib.loads(texte)
    except tomllib.TOMLDecodeError as e:
        return [], [f"equipe.toml illisible : {e}"]
    gardes, erreurs = [], []
    for m in donnees.get("membre", [])[:MEMBRES_MAX]:
        nom, module = str(m.get("nom", "")), str(m.get("module", ""))
        args = m.get("args", [])
        if not NOM.match(nom) or not MODULE.match(module):
            erreurs.append(f"membre écarté (nom ou module invalide) : {nom or '?'} / {module or '?'}")
            continue
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            erreurs.append(f"membre écarté (args doit être une liste de textes) : {nom}")
            continue
        try:
            minutes = min(max(float(m.get("minutes", 5)), 0.5), MINUTES_MAX)
        except (TypeError, ValueError):
            minutes = 5
        gardes.append({"nom": nom, "module": module, "minutes": minutes, "args": args})
    return gardes, erreurs


def env_membre(environ):
    """Seules les clés gratuites passent ; tout autre secret est retiré."""
    return lancer.env_cloisonne(environ, CLES) | {"PYTHONUTF8": "1"}


def faire_tourner(liste, executer=subprocess.run, environ=None):
    environ = os.environ if environ is None else environ
    env, resultats, reste = env_membre(environ), [], TOTAL_MAX_S
    for m in liste:
        if reste < 30:
            resultats.append({"nom": m["nom"], "resultat": "sauté : temps de l'équipe épuisé"})
            continue
        (registre.DOSSIER / "equipe" / m["nom"]).mkdir(parents=True, exist_ok=True)
        delai = min(m["minutes"] * 60, reste)
        debut = datetime.now(timezone.utc)
        try:
            proc = executer([sys.executable, "-m", m["module"], *m["args"]], capture_output=True, text=True,
                            encoding="utf-8", timeout=delai, cwd=str(organisation.DOSSIER.parent), env=env)
            resultat = "ok" if proc.returncode == 0 else f"échec (code {proc.returncode})"
            sortie = (proc.stdout + proc.stderr)[-800:]
        except subprocess.TimeoutExpired:
            resultat, sortie = f"coupé après {delai / 60:.0f} min", ""
        duree = (datetime.now(timezone.utc) - debut).total_seconds()
        reste -= duree
        resultats.append({"nom": m["nom"], "date": debut.isoformat(timespec="seconds"), "duree_s": round(duree),
                          "resultat": resultat, "sortie": sortie})
        print(f"{m['nom']} : {resultat}")
    return resultats


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    pause = lancer.pause_active(["pilote", lancer.TOUT], registre.lire("pauses"))
    if pause:
        print(f"Équipe en pause ({pause['cible']})")
        return 0
    chemin = organisation.DOSSIER / "equipe.toml"
    if not chemin.exists():
        print("Pas d'équipe (organisation/equipe.toml absent)")
        return 0
    liste, erreurs = membres(chemin.read_text(encoding="utf-8"))
    resultats = [{"nom": "?", "resultat": e} for e in erreurs] + faire_tourner(liste)
    dossier = registre.DOSSIER / "equipe"
    dossier.mkdir(parents=True, exist_ok=True)
    with open(dossier / "journal.jsonl", "a", encoding="utf-8") as f:
        for r in resultats:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
