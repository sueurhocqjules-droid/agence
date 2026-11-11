"""Agent flux : garde les chaînes alimentées, du sujet écrit à la vidéo programmée, sans Claude.

Lancement : python -m agents.flux [--essai]
  --essai : montre ce qui serait rendu et programmé, sans rien pousser ni envoyer.

À chaque passage :
1. Compare les sujets du moteur (studio-rendu) aux vidéos déjà sur les chaînes (titre exact) : ce qui manque.
2. Ce qui manque et a un rendu sur studio-rendu : téléchargé, contrôlé (agence/controle.py), programmé au prochain créneau.
3. Ce qui manque sans rendu : poussé dans la file de studio-rendu (file/attente.txt), dont le rendu part tout seul.
   Le passage suivant (12 h plus tard) le programme.
Coût : 0 jeton. Quota YouTube : ~1 600 unités par envoi. Minutes de rendu : dépôt public, gratuites.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from agence import controle, registre, youtube

DEPOT_RENDU = "sueurhocqjules-droid/studio-rendu"
RENDU = Path(os.environ.get("RENDU_DIR") or Path(__file__).resolve().parents[2] / "studio-rendu")
PARIS = ZoneInfo("Europe/Paris")
CRENEAUX = {"en": (1, 18), "es": (2, 19), "pt": (16, 23)}  # heures de Paris, deux vidéos par jour et par chaîne
DELAI_MIN = timedelta(hours=2)    # jamais de sortie plus tôt : une date passée publierait aussitôt
ENVOIS_MAX = 4                    # par chaîne et par passage (Studio bloquait au-delà de 3 ou 4 par jour)
RENDUS_MAX = 6                    # par passage, une machine par vidéo


def gh(*args, binaire=False):
    sortie = subprocess.run(["gh", *args], capture_output=True, check=True, text=not binaire)
    return sortie.stdout


def ordre_sujets():
    """Les sujets dans l'ordre du moteur (src/sujets.ts), le plus ancien d'abord."""
    texte = (RENDU / "src" / "sujets.ts").read_text(encoding="utf-8")
    return re.search(r"SUJETS: Sujet\[\] = \[([^\]]+)\]", texte).group(1).replace(" ", "").split(",")


def lire_sujet(sujet):
    return (json.loads((RENDU / "sujets" / f"{sujet}.json").read_text(encoding="utf-8")),
            json.loads((RENDU / "sujets" / f"{sujet}.calcul.json").read_text(encoding="utf-8")))


def dernier_artefact(nom):
    reponse = json.loads(gh("api", f"repos/{DEPOT_RENDU}/actions/artifacts?name={nom}&per_page=5"))
    return next((a for a in reponse["artifacts"] if not a["expired"]), None)


def telecharger(artefact, dossier):
    archive = zipfile.ZipFile(io.BytesIO(gh("api", artefact["archive_download_url"], binaire=True)))
    nom = next(n for n in archive.namelist() if n.endswith("-yt.mp4"))
    archive.extract(nom, dossier)
    return Path(dossier) / nom


def rendu_en_cours():
    for statut in ("queued", "in_progress"):
        if json.loads(gh("api", f"repos/{DEPOT_RENDU}/actions/runs?status={statut}&per_page=1"))["total_count"]:
            return True
    return False


def pousser_file(noms):
    """Écrit la file et la pousse : le workflow Rendre de studio-rendu part sur ce push."""
    compositions = [f"{n.split('-')[0].capitalize()}-{n.split('-')[1].capitalize()}:{n}" for n in noms]
    subprocess.run(["git", "pull", "-q", "--rebase"], cwd=RENDU, check=True)
    (RENDU / "file").mkdir(exist_ok=True)
    (RENDU / "file" / "attente.txt").write_text("\n".join(compositions) + "\n", encoding="utf-8", newline="\n")
    subprocess.run(["git", "add", "file/attente.txt"], cwd=RENDU, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"File de rendu : {' '.join(noms)}"], cwd=RENDU, check=True)
    subprocess.run(["git", "push", "-q"], cwd=RENDU, check=True)


def creneaux(langue, pris, debut):
    """Créneaux libres de la chaîne à partir de debut, dans l'ordre."""
    jour = debut.astimezone(PARIS).date()
    while True:
        for heure in CRENEAUX[langue]:
            quand = datetime.combine(jour, time(heure), PARIS)
            if quand >= debut and quand not in pris:
                yield quand
        jour += timedelta(days=1)


def etat_chaine(client):
    """Titres présents et dates de sortie à venir d'une chaîne."""
    titres, sorties = set(), set()
    for v in youtube.videos(client, "snippet,status"):
        titres.add(v["snippet"]["title"])
        if v["status"].get("publishAt"):
            sorties.add(datetime.fromisoformat(v["status"]["publishAt"].replace("Z", "+00:00")))
    return titres, sorties


def envoyer(client, fichier, sujet_json, calcul_json, langue, quand):
    from googleapiclient.http import MediaFileUpload

    corps = {
        "snippet": {"title": sujet_json[langue]["titre"], "description": calcul_json["descriptions"][langue]},
        "status": {
            "privacyStatus": "private",  # reste privée jusqu'à publishAt
            "publishAt": quand.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": False,
        },
    }
    envoi = client.videos().insert(part="snippet,status", body=corps,
                                   media_body=MediaFileUpload(str(fichier), mimetype="video/mp4", chunksize=-1, resumable=True))
    reponse = None
    while reponse is None:
        _, reponse = envoi.next_chunk()
    return reponse["id"]


def deja_rejete(nom, artefact_id):
    return any(l["nom"] == nom and l["etat"] == "rejete" and f"artefact {artefact_id}" in l["note"]
               for l in registre.lire("stock"))


def stock(nom, langue, sujet, etat, sortie="", video_id="", note=""):
    registre.ajouter("stock", [{"nom": nom, "chaine": langue, "sujet": sujet, "etat": etat, "sortie_prevue": sortie,
                                "video_id": video_id, "maj": registre.maintenant(), "note": note}])


def passage(essai):
    from googleapiclient.errors import HttpError

    sujets = ordre_sujets()
    maintenant = datetime.now(timezone.utc)
    clients = {l: youtube.client(l) for l in youtube.CHAINES}
    etats = {l: etat_chaine(c) for l, c in clients.items()}
    manquants = [(s, l) for s in sujets for l in youtube.CHAINES if lire_sujet(s)[0][l]["titre"] not in etats[l][0]]
    print(f"{len(sujets)} sujets, {len(manquants)} vidéos manquantes : {' '.join(f'{s}-{l}' for s, l in manquants) or 'aucune'}")

    a_rendre, programmees, rejetees, envois, bloquees = [], [], [], {l: 0 for l in clients}, set()
    with tempfile.TemporaryDirectory() as dossier:
        for sujet, langue in manquants:
            nom = f"{sujet}-{langue}"
            artefact = dernier_artefact(nom)
            if not artefact:
                a_rendre.append(nom)
                continue
            if langue in bloquees or envois[langue] >= ENVOIS_MAX or deja_rejete(nom, artefact["id"]):
                continue
            fichier = telecharger(artefact, dossier)
            defauts, mesures = controle.controler(fichier)
            if defauts:
                print(f"REJET {nom} : {', '.join(defauts)}")
                rejetees.append(nom)
                if not essai:
                    stock(nom, langue, sujet, "rejete", note=f"artefact {artefact['id']} : {', '.join(defauts)}")
                continue
            titres, sorties = etats[langue]
            debut = max([maintenant + DELAI_MIN] + [s + timedelta(minutes=1) for s in sorties])
            quand = next(creneaux(langue, sorties, debut))
            if essai:
                print(f"ESSAI {nom} -> {quand:%d/%m %H:%M} Paris, {mesures}")
                continue
            sujet_json, calcul_json = lire_sujet(sujet)
            try:
                video_id = envoyer(clients[langue], fichier, sujet_json, calcul_json, langue, quand)
            except HttpError as e:
                raison = next((r for r in ("uploadLimitExceeded", "quotaExceeded") if r.encode() in e.content), None)
                if raison:
                    print(f"LIMITE {nom} ({raison}) : plus d'envoi sur cette chaîne pour ce passage")
                    bloquees.add(langue)
                    continue
                raise
            sorties.add(quand)
            titres.add(sujet_json[langue]["titre"])
            envois[langue] += 1
            programmees.append(nom)
            stock(nom, langue, sujet, "programme", quand.astimezone(timezone.utc).isoformat(), video_id,
                  f"artefact {artefact['id']}, {mesures}")
            print(f"OK {nom} : {video_id}, sortie {quand:%d/%m %H:%M} Paris")

    a_rendre = a_rendre[:RENDUS_MAX]
    if a_rendre and rendu_en_cours():
        print("Rendu déjà en cours sur studio-rendu : file inchangée")
        a_rendre = []
    if a_rendre and not essai:
        pousser_file(a_rendre)
        for nom in a_rendre:
            sujet, langue = nom.split("-")
            stock(nom, langue, sujet, "en_rendu")
    print(f"À rendre : {' '.join(a_rendre) or 'rien'}")
    return programmees, rejetees, a_rendre


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--essai" in sys.argv:
        passage(essai=True)  # rien n'est écrit, pas même le coût
        return
    with registre.seance("flux") as info:
        programmees, rejetees, a_rendre = passage(essai=False)
        info["resultat"] = f"ok : {len(programmees)} programmées, {len(rejetees)} rejetées, {len(a_rendre)} en rendu"
        print(info["resultat"])
    if rejetees:
        sys.exit(1)  # le réveil passe au rouge : un défaut demande un regard


if __name__ == "__main__":
    main()
