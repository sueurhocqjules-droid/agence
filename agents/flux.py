"""Agent flux : garde les chaînes alimentées, du sujet écrit à la vidéo programmée, sans Claude.

Lancement : python -m agents.flux [--essai]
  --essai : montre ce qui serait rendu et programmé, sans rien pousser ni envoyer.

À chaque passage :
1. Compare les sujets du moteur (studio-rendu) aux vidéos déjà sur les chaînes (titre exact) : ce qui manque.
2. Ce qui manque et a un rendu sur studio-rendu : téléchargé, contrôlé (agence/controle.py), programmé au prochain créneau.
3. Diffusion : chaque vidéo déjà publique sur YouTube part en Reel sur le compte Instagram et la Page Facebook de sa
   langue (agence/meta.py), la plus ancienne d'abord, au rythme fixé par le Programmateur (organisation/diffusion.toml).
   Facebook n'accepte pas plus de 90 s : une vidéo plus longue y est notée « hors_format » et sautée.
   Instagram : on ne publie qu'une fois le conteneur FINISHED. Un envoi refusé note le code et le message de Meta
   au registre des diffusions et, comme bloquant, au journal du Pilote ; il est retenté au réveil suivant,
   3 fois au plus par vidéo, puis la suivante passe.
   TikTok : par Buffer (agence/buffer.py), même règle, même cadence ; une chaîne pas encore branchée sur Buffer est sautée.
   Threads : agence/threads.py, un jeton par compte (renouvelé ici même) ; un compte pas encore branché est sauté.
4. Ce qui manque sans rendu (ou dont le rendu a expiré avant sa diffusion) : poussé dans la file de studio-rendu
   (file/attente.txt), dont le rendu part tout seul. Le passage suivant le programme ou le diffuse.
Coût : 0 jeton. Quota YouTube : ~1 600 unités par envoi. Minutes de rendu : dépôt public, gratuites.
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from agence import buffer, controle, lancer, meta, mesures, registre, threads, youtube

DEPOT_RENDU = "sueurhocqjules-droid/studio-rendu"
RENDU = Path(os.environ.get("RENDU_DIR") or Path(__file__).resolve().parents[2] / "studio-rendu")
PARIS = ZoneInfo("Europe/Paris")
DELAI_MIN = timedelta(hours=2)    # jamais de sortie plus tôt : une date passée publierait aussitôt
ENVOIS_MAX = 4                    # par chaîne et par passage (Studio bloquait au-delà de 3 ou 4 par jour)
# Plafonds par jour, quoi que disent creneaux.toml et diffusion.toml (réglages du Pilote) : ce fichier est protégé
SORTIES_JOUR_MAX = 4              # sorties YouTube par chaîne : limite d'envoi de YouTube vécue le 11/11 (uploadLimitExceeded, téléphone non vérifié)
DIFFUSION_JOUR_MAX = 25           # diffusions par réseau et par chaîne : anti-emballement, sous Buffer (25 TikTok / 24 h) et Facebook (30 Reels / 24 h)
RENDUS_MAX = 12                   # par passage, une machine par vidéo
DIFFUSION = Path(__file__).resolve().parents[1] / "organisation" / "diffusion.toml"
REELS_FACEBOOK_MAX_S = 90         # Reels des Pages : 3 à 90 s


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


def sujets_lisibles(sujets, lire=lire_sujet):
    """Les sujets complets (titre par chaîne, description par langue). Un sujet mal formé est sauté et dit, sans
    arrêter la publication des autres."""
    bons = []
    for s in sujets:
        try:
            sujet_json, calcul_json = lire(s)
            for langue in youtube.CHAINES:
                if not (isinstance(sujet_json[langue]["titre"], str) and isinstance(calcul_json["descriptions"][langue], str)):
                    raise TypeError("titre ou description qui n'est pas un texte")
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"SUJET ILLISIBLE {s} : {type(e).__name__} {e}"[:300] + ", sauté")
            continue
        bons.append(s)
    return bons


def dernier_artefact(nom):
    reponse = json.loads(gh("api", f"repos/{DEPOT_RENDU}/actions/artifacts?name={nom}&per_page=5"))
    return next((a for a in reponse["artifacts"] if not a["expired"]), None)


def telecharger(artefact, dossier):
    archive = zipfile.ZipFile(io.BytesIO(gh("api", artefact["archive_download_url"], binaire=True)))
    nom = next((n for n in archive.namelist() if n.endswith("-yt.mp4")), None)
    if not nom:  # rendu sans sa version YouTube (compression ratée) : on le refait
        return None
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
    # Ligne datée sans « : », ignorée par studio-rendu : la même file redemandée (rendu raté) fait quand même un commit
    marque = f"#demande-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}"
    (RENDU / "file" / "attente.txt").write_text("\n".join(compositions + [marque]) + "\n", encoding="utf-8",
                                               newline="\n")
    subprocess.run(["git", "add", "file/attente.txt"], cwd=RENDU, check=True)
    subprocess.run(["git", "commit", "-q", "-m", f"File de rendu : {' '.join(noms)}"], cwd=RENDU, check=True)
    subprocess.run(["git", "push", "-q"], cwd=RENDU, check=True)


def creneaux(heures, pris, debut):
    """Créneaux libres d'une chaîne (ses heures de sortie, à Paris) à partir de debut, dans l'ordre. Heures invalides
    ignorées, SORTIES_JOUR_MAX par jour au plus ; aucune heure valide : aucun créneau."""
    heures = sorted({h for h in heures if type(h) is int and 0 <= h <= 23})
    if len(heures) > SORTIES_JOUR_MAX:     # étalées sur la journée, pas les premières heures
        pas = (len(heures) - 1) / (SORTIES_JOUR_MAX - 1)
        heures = [heures[round(i * pas)] for i in range(SORTIES_JOUR_MAX)]
    if not heures:
        return
    jour = debut.astimezone(PARIS).date()
    while True:
        for heure in sorted(heures):
            quand = datetime.combine(jour, time(heure), PARIS)
            if quand >= debut and quand not in pris:
                yield quand
        jour += timedelta(days=1)


def etat_chaine(client):
    """Titres présents, dates de sortie à venir et titres déjà publics d'une chaîne."""
    titres, sorties, publics = set(), set(), set()
    for v in youtube.videos(client, "snippet,status"):
        titres.add(v["snippet"]["title"])
        if v["status"].get("publishAt"):
            sorties.add(datetime.fromisoformat(v["status"]["publishAt"].replace("Z", "+00:00")))
        if v["status"].get("privacyStatus") == "public":
            publics.add(v["snippet"]["title"])
    return titres, sorties, publics


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


def cadence_diffusion():
    """{reseau: sorties par jour}, réglé par le Pilote, borné à DIFFUSION_JOUR_MAX (valeur illisible : 0)."""
    with open(DIFFUSION, "rb") as f:
        reglage = tomllib.load(f)
    cadence = {}
    for reseau, r in reglage.items():
        n = r.get("par_jour") if isinstance(r, dict) else None
        cadence[reseau] = min(n, DIFFUSION_JOUR_MAX) if type(n) is int and n > 0 else 0
    return cadence


ESSAIS_INSTAGRAM_MAX = 3  # un envoi Instagram refusé est retenté au réveil suivant, 3 fois au plus


def essais_rates(lignes, reseau, nom):
    """Nombre d'envois déjà refusés (état « erreur ») de cette vidéo sur ce réseau."""
    return sum(1 for l in lignes if l["reseau"] == reseau and l["nom"] == nom and l["etat"] == "erreur")


def diffusion(reseau, langue, nom, etat, media_id="", note=""):
    registre.ajouter("diffusions", [{"date": registre.maintenant(), "reseau": reseau, "chaine": langue, "nom": nom,
                                     "etat": etat, "media_id": media_id, "note": note}])
    if reseau == "instagram" and etat == "erreur":  # un envoi refusé est un bloquant au journal du Pilote
        lancer.noter_journal("pilote", {"date": registre.maintenant(), "quoi": f"diffusion instagram {nom}",
                                              "resultat": "erreur",
                                              "bloquant": f"envoi instagram refusé pour {nom} ({note})"[:400]})


def publies_aujourdhui(lignes, reseau, langue, maintenant):
    jour = maintenant.astimezone(PARIS).date()
    return sum(1 for l in lignes if l["reseau"] == reseau and l["chaine"] == langue and l["etat"] == "publie"
               and datetime.fromisoformat(l["date"]).astimezone(PARIS).date() == jour)


def a_diffuser(sujets, titres_publics, deja, sautes, langue):
    """Sujets publics sur YouTube, pas encore sur le réseau ni sautés, du plus ancien au plus récent."""
    return [s for s in sujets if (t := lire_sujet(s)[0][langue]["titre"]) in titres_publics
            and t not in deja and f"{s}-{langue}" not in sautes]


def noter_refus_instagram(nom, erreur):
    """Un envoi Instagram refusé remonte comme bloquant au journal du Pilote, avec la réponse complète de l'API :
    sans la cause on ne peut rien corriger."""
    reponse = getattr(erreur, "reponse", None) or {"message": str(erreur)}
    lancer.noter_journal("pilote", {"date": registre.maintenant(), "quoi": "diffusion", "resultat": "erreur",
                                          "bloquant": f"Instagram a refusé {nom} : "
                                                      f"{json.dumps(reponse, ensure_ascii=False)}"})


def diffuser(essai, sujets, etats, pauses, dossier, maintenant, fichiers=None):
    """Reels Instagram et Facebook des vidéos déjà publiques sur YouTube. Renvoie (publiées, erreurs, à rendre).
    fichiers : rendus déjà téléchargés et contrôlés ({nom: (fichier, durée) ou None}), partagés avec TikTok."""
    if not meta.jeton():
        print("Diffusion Meta : pas de jeton (META_TOKEN), rien envoyé")
        return [], [], []
    cadence = cadence_diffusion()
    lignes = registre.lire("diffusions")
    comptes_ig = meta.comptes_instagram()
    publiees, erreurs, a_rendre = [], [], []
    fichiers = {} if fichiers is None else fichiers
    for langue in youtube.CHAINES:
        for reseau in ("instagram", "facebook"):
            ligne = lancer.pause_active([f"chaine:{langue}", f"{reseau}:{langue}", f"reseau:{reseau}"], pauses)
            if ligne:
                print(f"PAUSE {reseau} {langue} ({ligne['par']} : {ligne['raison']}) : aucune diffusion")
                continue
            restant = cadence.get(reseau, 0) - publies_aujourdhui(lignes, reseau, langue, maintenant)
            if restant <= 0:
                continue
            if reseau == "instagram":
                if langue not in comptes_ig:
                    print(f"Instagram {langue} : compte {meta.INSTAGRAM[langue]} non assigné à l'utilisateur système")
                    continue
                cle_page, deja = None, meta.titres_instagram(comptes_ig[langue])
            else:
                cle_page = meta.jeton_page(meta.PAGES[langue])
                deja = meta.titres_facebook(meta.PAGES[langue], cle_page)
            sautes = {l["nom"] for l in lignes if l["reseau"] == reseau and l["etat"] == "hors_format"}
            for sujet in a_diffuser(sujets, etats[langue][2], deja, sautes, langue):
                if restant <= 0:
                    break
                nom = f"{sujet}-{langue}"
                if nom not in fichiers:
                    fichiers[nom] = fichier_controle(nom, dossier)
                if reseau == "instagram" and essais_rates(lignes, reseau, nom) >= ESSAIS_INSTAGRAM_MAX:
                    continue  # 3 refus déjà notés : on n'insiste plus, la suivante passe
                if not fichiers[nom]:
                    if nom not in a_rendre:
                        a_rendre.append(nom)  # rendu expiré ou incomplet : refait, diffusé au passage suivant
                    restant -= 1  # pas plus de rendus que de places du jour
                    continue
                fichier, duree = fichiers[nom]
                if reseau == "facebook" and duree > REELS_FACEBOOK_MAX_S:
                    print(f"HORS FORMAT facebook {nom} : {duree:.0f} s, plus de {REELS_FACEBOOK_MAX_S} s")
                    if not essai:
                        diffusion(reseau, langue, nom, "hors_format", note=f"{duree:.0f} s")
                    continue
                if essai:
                    print(f"ESSAI diffusion {reseau} {nom}")
                    restant -= 1
                    continue
                sujet_json, calcul_json = lire_sujet(sujet)
                titre, description = sujet_json[langue]["titre"], calcul_json["descriptions"][langue]
                try:
                    if reseau == "instagram":
                        media_id = meta.publier_instagram(comptes_ig[langue], heberger(fichier), titre, description)
                    else:
                        media_id = meta.publier_facebook(meta.PAGES[langue], cle_page, fichier, titre, description)
                except meta.ErreurMeta as e:
                    print(f"ERREUR {reseau} {nom} : {e}")
                    diffusion(reseau, langue, nom, "erreur", note=f"code {e.code or '?'} : {e}"[:300])
                    erreurs.append(f"{reseau}:{nom}")
                    if reseau == "instagram":
                        noter_refus_instagram(nom, e)
                    break  # limite atteinte ou accès coupé : plus rien sur ce compte pour ce passage
                diffusion(reseau, langue, nom, "publie", media_id)
                publiees.append(f"{reseau}:{nom}")
                restant -= 1
                print(f"OK {reseau} {nom} : {media_id}")
    return publiees, erreurs, a_rendre


def diffuser_threads(essai, sujets, etats, pauses, dossier, maintenant, fichiers=None):
    """Vidéos déjà publiques sur YouTube vers Threads (agence/threads.py), au rythme de diffusion.toml. Renouvelle
    d'abord les jetons des comptes branchés (même si la cadence est à 0, pour ne pas les perdre) ; un problème de
    jeton est noté au registre des diffusions. Renvoie (publiées, erreurs, à rendre)."""
    fichiers = {} if fichiers is None else fichiers
    try:
        comptes = threads.lire()
    except threads.ErreurThreads as e:
        print(f"ERREUR threads : {e}")
        if not essai:
            diffusion("threads", "", "", "erreur", note=str(e)[:300])
        return [], ["threads:jetons"], []
    if not comptes:
        print("Diffusion Threads : aucun compte branché (python -m agence.threads brancher), rien envoyé")
        return [], [], []
    erreurs = []
    if not essai:
        renouveles, problemes = threads.renouveler(comptes, maintenant)
        if renouveles != comptes:
            threads.ecrire(renouveles)
            comptes = renouveles
        for probleme in problemes:
            print(f"ERREUR threads {probleme}")
            diffusion("threads", probleme.split(" ")[0], "", "erreur", note=probleme[:300])
            erreurs.append(f"threads:{probleme.split(' ')[0]}")
    par_jour = cadence_diffusion().get("threads", 0)
    if par_jour <= 0:
        return [], erreurs, []
    lignes = registre.lire("diffusions")
    sautes = {l["nom"] for l in lignes if l["reseau"] == "threads" and l["etat"] == "hors_format"}
    publiees, a_rendre = [], []
    for langue in youtube.CHAINES:
        ligne = lancer.pause_active([f"chaine:{langue}", f"threads:{langue}", "reseau:threads"], pauses)
        if ligne:
            print(f"PAUSE threads {langue} ({ligne['par']} : {ligne['raison']}) : aucune diffusion")
            continue
        restant = par_jour - publies_aujourdhui(lignes, "threads", langue, maintenant)
        if restant <= 0:
            continue
        if langue not in comptes:
            print(f"Threads {langue} : @{threads.COMPTES[langue]} pas branché, sauté")
            continue
        try:
            deja = threads.titres(comptes[langue])
        except threads.ErreurThreads as e:
            print(f"ERREUR threads {langue} : lecture des posts : {e}")
            erreurs.append(f"threads:{langue}")
            continue
        for sujet in a_diffuser(sujets, etats[langue][2], deja, sautes, langue):
            if restant <= 0:
                break
            nom = f"{sujet}-{langue}"
            if nom not in fichiers:
                fichiers[nom] = fichier_controle(nom, dossier)
            if not fichiers[nom]:
                if nom not in a_rendre:
                    a_rendre.append(nom)
                restant -= 1
                continue
            fichier, duree = fichiers[nom]
            if duree > threads.DUREE_MAX_S:
                print(f"HORS FORMAT threads {nom} : {duree:.0f} s, plus de {threads.DUREE_MAX_S} s")
                if not essai:
                    diffusion("threads", langue, nom, "hors_format", note=f"{duree:.0f} s")
                continue
            restant -= 1
            if essai:
                print(f"ESSAI diffusion threads {nom}")
                continue
            sujet_json, calcul_json = lire_sujet(sujet)
            try:
                media_id = threads.publier(comptes[langue], heberger(fichier), sujet_json[langue]["titre"],
                                           calcul_json["descriptions"][langue])
            except threads.ErreurThreads as e:
                print(f"ERREUR threads {nom} : {e}")
                diffusion("threads", langue, nom, "erreur", note=str(e)[:300])
                erreurs.append(f"threads:{nom}")
                break  # limite atteinte ou accès coupé : plus rien sur ce compte pour ce passage
            diffusion("threads", langue, nom, "publie", media_id)
            publiees.append(f"threads:{nom}")
            print(f"OK threads {nom} : {media_id}")
    return publiees, erreurs, a_rendre


def diffuser_tiktok(essai, sujets, etats, pauses, dossier, maintenant, fichiers=None):
    """Vidéos déjà publiques sur YouTube vers TikTok, par Buffer (agence/buffer.py), au rythme de diffusion.toml.
    Chaînes et vidéos déjà envoyées lues dans Buffer ; une chaîne pas encore branchée est sautée et notée au journal.
    Toutes les vidéos du passage sont hébergées dans un seul commit (Buffer les lit après coup), puis chaque post est
    relu jusqu'à son envoi. Renvoie (publiées, erreurs, à rendre)."""
    fichiers = {} if fichiers is None else fichiers
    par_jour = cadence_diffusion().get("tiktok", 0)
    if par_jour <= 0:
        return [], [], []
    if not buffer.jeton():
        print("Diffusion TikTok : pas de clé Buffer (BUFFER_API_KEY), rien envoyé")
        return [], [], []
    lignes = registre.lire("diffusions")
    try:
        org = buffer.organisation()
        chaines = buffer.chaines_tiktok(org)
    except buffer.ErreurBuffer as e:
        print(f"ERREUR tiktok : accès à Buffer : {e}")
        if not essai:
            diffusion("tiktok", "", "", "erreur", note=f"accès à Buffer : {e}"[:300])
        return [], ["tiktok:buffer"], []
    publiees, erreurs, a_rendre, envois = [], [], [], []
    for langue in youtube.CHAINES:
        ligne = lancer.pause_active([f"chaine:{langue}", f"tiktok:{langue}", "reseau:tiktok"], pauses)
        if ligne:
            print(f"PAUSE tiktok {langue} ({ligne['par']} : {ligne['raison']}) : aucune diffusion")
            continue
        restant = par_jour - publies_aujourdhui(lignes, "tiktok", langue, maintenant)
        if restant <= 0:
            continue
        if langue not in chaines:
            print(f"TikTok {langue} : @{buffer.TIKTOK[langue]} pas branché sur Buffer, sauté")
            continue
        try:
            deja = buffer.posts(org, chaines[langue])
        except buffer.ErreurBuffer as e:
            print(f"ERREUR tiktok {langue} : lecture des posts : {e}")
            erreurs.append(f"tiktok:{langue}")
            continue
        place = buffer.FILE_MAX - buffer.en_file(deja)
        if place < restant:
            print(f"TikTok {langue} : file Buffer à {buffer.FILE_MAX - place}/{buffer.FILE_MAX}, {max(place, 0)} envoi(s) au plus")
            restant = place
        sautes = {l["nom"] for l in lignes if l["reseau"] == "tiktok" and l["etat"] == "hors_format"}
        for sujet in a_diffuser(sujets, etats[langue][2], buffer.titres(deja), sautes, langue):
            if restant <= 0:
                break
            nom = f"{sujet}-{langue}"
            if nom not in fichiers:
                fichiers[nom] = fichier_controle(nom, dossier)
            if not fichiers[nom]:
                if nom not in a_rendre:
                    a_rendre.append(nom)
                restant -= 1
                continue
            fichier, duree = fichiers[nom]
            if not buffer.DUREE_MIN_S <= duree <= buffer.DUREE_MAX_S:
                print(f"HORS FORMAT tiktok {nom} : {duree:.0f} s")
                if not essai:
                    diffusion("tiktok", langue, nom, "hors_format", note=f"{duree:.0f} s")
                continue
            restant -= 1
            if essai:
                print(f"ESSAI diffusion tiktok {nom}")
                continue
            envois.append((langue, sujet, nom, fichier))
    if not envois:
        return publiees, erreurs, a_rendre

    adresses = heberger_tous([f for *_, f in envois])
    crees, bloquees = {}, set()
    for langue, sujet, nom, fichier in envois:
        if langue in bloquees:
            continue
        sujet_json, calcul_json = lire_sujet(sujet)
        texte = buffer.legende(sujet_json[langue]["titre"], calcul_json["descriptions"][langue])
        try:
            # isAiGenerated : seulement pour des personnes ou scènes réalistes générées par IA ; les vidéos du moteur
            # sont des animations calculées. Un futur concept qui en montre pose "ia_realiste": true dans son sujet
            post_id = buffer.publier(chaines[langue], adresses[fichier], texte, sujet_json.get("ia_realiste", False))
        except buffer.ErreurBuffer as e:
            print(f"ERREUR tiktok {nom} : {e}")
            diffusion("tiktok", langue, nom, "erreur", note=str(e)[:300])
            erreurs.append(f"tiktok:{nom}")
            bloquees.add(langue)  # limite atteinte ou accès coupé : plus rien sur ce compte pour ce passage
            continue
        crees[post_id] = (langue, nom)
        print(f"ENVOYÉ tiktok {nom} : post Buffer {post_id}")
    if not crees:
        return publiees, erreurs, a_rendre
    try:
        relus = buffer.confirmer(org, {i: chaines[l] for i, (l, _) in crees.items()})
    except buffer.ErreurBuffer as e:
        print(f"Relecture des posts TikTok impossible ({e}) : notés comme envoyés")
        relus = {}
    for post_id, (langue, nom) in crees.items():
        post = relus.get(post_id, {})
        etat = buffer.statut(post) or "inconnu"
        if etat == "error":
            message = (post.get("error") or {}).get("message") or "erreur sans message"
            print(f"ERREUR tiktok {nom} : Buffer n'a pas publié ({message})")
            diffusion("tiktok", langue, nom, "erreur", post_id, note=message[:300])
            erreurs.append(f"tiktok:{nom}")
            continue
        note = (post.get("externalLink") or "") if etat == "sent" else f"statut {etat} à la fin du passage"
        diffusion("tiktok", langue, nom, "publie", post_id, note=note)
        publiees.append(f"tiktok:{nom}")
        print(f"OK tiktok {nom} : {etat} {post.get('externalLink') or ''}".rstrip())
    return publiees, erreurs, a_rendre


def heberger(fichier):
    """Met la vidéo seule sur la branche « diffusion » du dépôt public studio-rendu et renvoie son adresse publique,
    que Meta lit pour Instagram."""
    return heberger_tous([fichier])[fichier]


def heberger_tous(fichiers):
    """Met les vidéos sur la branche « diffusion » du dépôt public studio-rendu (clé de déploiement déjà utilisée pour
    la file), en un seul commit, et renvoie {fichier: adresse publique}. Chaque envoi remplace le précédent : la branche
    ne garde que les vidéos du dernier envoi et ne déclenche aucun rendu (seul main le fait)."""
    def git(*args, entree=None):
        return subprocess.run(["git", *args], cwd=RENDU, check=True, capture_output=True, text=True,
                              input=entree).stdout.strip()
    # -z : pas de \r sous Windows ; mktree trie lui-même les entrées
    arbre = git("mktree", "-z", entree="".join(f"100644 blob {git('hash-object', '-w', str(f))}\t{Path(f).name}\0"
                                                for f in fichiers))
    commit = git("commit-tree", arbre, "-m", f"Diffusion : {' '.join(Path(f).name for f in fichiers)}")
    git("push", "-q", "-f", "origin", f"{commit}:refs/heads/diffusion")
    return {f: f"https://raw.githubusercontent.com/{DEPOT_RENDU}/{commit}/{Path(f).name}" for f in fichiers}


def fichier_controle(nom, dossier):
    """(fichier, durée en s) du dernier rendu encore disponible et sans défaut, sinon None."""
    artefact = dernier_artefact(nom)
    fichier = artefact and telecharger(artefact, dossier)
    if not fichier:
        return None
    defauts, releve = controle.controler(fichier)
    return None if defauts else (fichier, releve["duree_s"])


def passage(essai):
    from googleapiclient.errors import HttpError

    sujets = sujets_lisibles(ordre_sujets())
    heures = mesures.heures_de_sortie()  # réglées par le Programmateur (organisation/creneaux.toml)
    maintenant = datetime.now(timezone.utc)
    clients = {l: youtube.client(l) for l in youtube.CHAINES}
    etats = {l: etat_chaine(c) for l, c in clients.items()}
    manquants = [(s, l) for s in sujets for l in youtube.CHAINES if lire_sujet(s)[0][l]["titre"] not in etats[l][0]]
    print(f"{len(sujets)} sujets, {len(manquants)} vidéos manquantes : {' '.join(f'{s}-{l}' for s, l in manquants) or 'aucune'}")

    a_rendre, programmees, rejetees, envois, bloquees = [], [], [], {l: 0 for l in clients}, set()
    pauses = registre.lire("pauses")
    for l in clients:  # une chaîne en pause (par la Sûreté ou par Jules) ne reçoit plus rien
        ligne = lancer.pause_active([f"chaine:{l}"], pauses)
        if ligne:
            print(f"PAUSE chaîne {l} ({ligne['par']} : {ligne['raison']}) : aucun envoi")
            bloquees.add(l)
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
            if not fichier:
                print(f"INCOMPLET {nom} : artefact {artefact['id']} sans -yt.mp4, à rendre de nouveau")
                a_rendre.append(nom)
                continue
            defauts, releve = controle.controler(fichier)
            if defauts:
                print(f"REJET {nom} : {', '.join(defauts)}")
                rejetees.append(nom)
                if not essai:
                    stock(nom, langue, sujet, "rejete", note=f"artefact {artefact['id']} : {', '.join(defauts)}")
                continue
            titres, sorties, _ = etats[langue]
            debut = max([maintenant + DELAI_MIN] + [s + timedelta(minutes=1) for s in sorties])
            quand = next(creneaux(heures.get(langue, []), sorties, debut), None)
            if quand is None:
                print(f"PAS DE CRÉNEAU {nom} : aucune heure de sortie valide pour {langue} dans creneaux.toml")
                continue
            if essai:
                print(f"ESSAI {nom} -> {quand:%d/%m %H:%M} Paris, {releve}")
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
                  f"artefact {artefact['id']}, {releve}")
            print(f"OK {nom} : {video_id}, sortie {quand:%d/%m %H:%M} Paris")

        fichiers = {}  # rendus téléchargés une seule fois pour tous les réseaux
        diffusees, erreurs, pour_diffuser = diffuser(essai, sujets, etats, pauses, dossier, maintenant, fichiers)
        tiktok = diffuser_tiktok(essai, sujets, etats, pauses, dossier, maintenant, fichiers)
        diffusees, erreurs, pour_diffuser = diffusees + tiktok[0], erreurs + tiktok[1], pour_diffuser + tiktok[2]
        fils = diffuser_threads(essai, sujets, etats, pauses, dossier, maintenant, fichiers)
        diffusees, erreurs, pour_diffuser = diffusees + fils[0], erreurs + fils[1], pour_diffuser + fils[2]
        a_rendre += [n for n in dict.fromkeys(pour_diffuser) if n not in a_rendre]  # YouTube d'abord, puis la diffusion

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
    return programmees, rejetees, a_rendre, diffusees, erreurs


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "--essai" in sys.argv:
        passage(essai=True)  # rien n'est écrit, pas même le coût
        return
    with registre.seance("flux") as info:
        programmees, rejetees, a_rendre, diffusees, erreurs = passage(essai=False)
        info["resultat"] = (f"ok : {len(programmees)} programmées, {len(rejetees)} rejetées, {len(a_rendre)} en rendu, "
                            f"{len(diffusees)} diffusées, {len(erreurs)} erreurs de diffusion")
        print(info["resultat"])
    if rejetees or erreurs:
        sys.exit(1)  # le réveil passe au rouge : un défaut demande un regard


if __name__ == "__main__":
    main()
