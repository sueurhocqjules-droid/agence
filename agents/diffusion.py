"""Diffusion planifiée : publie sur Instagram, Facebook et TikTok les vidéos de organisation/planning-diffusion.csv.

Relais temporaire, posé par Claude dans Jarvis le 23/11 : le Pilote est en pause depuis le 18/11 et flux avec lui,
donc plus rien ne partait sur les réseaux. Ce script tourne hors pause, ne fabrique rien et ne touche pas à YouTube :
il lit le planning (une ligne par réseau et par vidéo, avec l'heure à partir de laquelle elle peut partir et l'adresse
de la vidéo hébergée sur studio-rendu), publie ce qui est dû et le note dans registre/diffusions.csv.

Garde-fous :
- une vidéo déjà notée « publie » sur ce réseau, ou dont le titre est déjà en ligne sur le compte, n'est pas renvoyée ;
- au plus PAR_PASSAGE vidéos par réseau et par langue à chaque réveil ;
- une vidéo refusée ESSAIS_MAX fois est abandonnée ; un refus arrête le compte pour ce passage.
"""
import csv
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from agence import buffer, meta, registre
from agents.flux import diffusion, essais_rates

PLANNING = Path(__file__).resolve().parent.parent / "organisation" / "planning-diffusion.csv"
RESEAUX = ("instagram", "facebook", "tiktok")
PAR_PASSAGE = 2
ESSAIS_MAX = 3


def lire_planning(chemin=PLANNING):
    if not chemin.exists():
        return []
    with open(chemin, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def dues(planning, lignes, maintenant):
    """Lignes à publier maintenant, regroupées par (réseau, langue) : l'heure est passée, la vidéo n'est ni publiée
    ni abandonnée après ESSAIS_MAX refus, et au plus PAR_PASSAGE par compte, la plus ancienne d'abord."""
    faites = {(l["reseau"], l["nom"]) for l in lignes if l["etat"] == "publie"}
    groupes = {}
    for p in sorted(planning, key=lambda p: p["apres_utc"]):
        if datetime.fromisoformat(p["apres_utc"]) > maintenant or (p["reseau"], p["nom"]) in faites:
            continue
        if essais_rates(lignes, p["reseau"], p["nom"]) >= ESSAIS_MAX:
            continue
        groupe = groupes.setdefault((p["reseau"], p["langue"]), [])
        if len(groupe) < PAR_PASSAGE:
            groupe.append(p)
    return groupes


def telecharger(adresse, dossier):
    fichier = Path(dossier) / adresse.rsplit("/", 1)[1]
    urllib.request.urlretrieve(adresse, fichier)
    return fichier


def publier_meta(reseau, langue, lignes_dues, comptes_ig, dossier):
    if reseau == "instagram":
        if langue not in comptes_ig:
            print(f"Instagram {langue} : compte {meta.INSTAGRAM[langue]} non assigné, sauté")
            return
        deja = meta.titres_instagram(comptes_ig[langue])
    else:
        cle_page = meta.jeton_page(meta.PAGES[langue])
        deja = meta.titres_facebook(meta.PAGES[langue], cle_page)
    for p in lignes_dues:
        if p["titre"] in deja:
            print(f"DÉJÀ EN LIGNE {reseau} {p['nom']}")
            diffusion(reseau, langue, p["nom"], "publie", note="déjà en ligne, constaté par diffusion")
            continue
        try:
            if reseau == "instagram":
                media_id = meta.publier_instagram(comptes_ig[langue], p["adresse"], p["titre"], p["texte"])
            else:
                media_id = meta.publier_facebook(meta.PAGES[langue], cle_page, telecharger(p["adresse"], dossier),
                                                 p["titre"], p["texte"])
        except meta.ErreurMeta as e:
            print(f"ERREUR {reseau} {p['nom']} : {e}")
            diffusion(reseau, langue, p["nom"], "erreur", note=f"code {e.code or '?'} : {e}"[:300])
            return  # limite atteinte ou accès coupé : plus rien sur ce compte pour ce passage
        diffusion(reseau, langue, p["nom"], "publie", media_id)
        print(f"OK {reseau} {p['nom']} : {media_id}")


def publier_tiktok(langue, lignes_dues, org, chaines):
    if langue not in chaines:
        print(f"TikTok {langue} : pas branché sur Buffer, sauté")
        return
    deja = buffer.titres(buffer.posts(org, chaines[langue]))
    crees = {}
    for p in lignes_dues:
        if p["titre"] in deja:
            print(f"DÉJÀ EN LIGNE tiktok {p['nom']}")
            diffusion("tiktok", langue, p["nom"], "publie", note="déjà en ligne, constaté par diffusion")
            continue
        try:
            crees[buffer.publier(chaines[langue], p["adresse"], buffer.legende(p["titre"], p["texte"]), False)] = p
        except buffer.ErreurBuffer as e:
            print(f"ERREUR tiktok {p['nom']} : {e}")
            diffusion("tiktok", langue, p["nom"], "erreur", note=str(e)[:300])
            break
    if not crees:
        return
    try:
        relus = buffer.confirmer(org, {i: chaines[langue] for i in crees})
    except buffer.ErreurBuffer as e:
        print(f"Relecture des posts TikTok impossible ({e}) : notés comme envoyés")
        relus = {}
    for post_id, p in crees.items():
        post = relus.get(post_id, {})
        etat = buffer.statut(post) or "inconnu"
        if etat == "error":
            message = (post.get("error") or {}).get("message") or "erreur sans message"
            print(f"ERREUR tiktok {p['nom']} : Buffer n'a pas publié ({message})")
            diffusion("tiktok", langue, p["nom"], "erreur", post_id, note=message[:300])
            continue
        diffusion("tiktok", langue, p["nom"], "publie", post_id,
                  note=(post.get("externalLink") or "") if etat == "sent" else f"statut {etat} à la fin du passage")
        print(f"OK tiktok {p['nom']} : {etat}")


def main():
    groupes = dues(lire_planning(), registre.lire("diffusions"), datetime.now(timezone.utc))
    if not groupes:
        print("Rien de dû dans le planning de diffusion")
        return
    erreurs = 0
    with tempfile.TemporaryDirectory() as dossier:
        comptes_ig, org, chaines = None, None, None
        for (reseau, langue), lignes_dues in groupes.items():
            try:
                if reseau == "tiktok":
                    if org is None:
                        org = buffer.organisation()
                        chaines = buffer.chaines_tiktok(org)
                    publier_tiktok(langue, lignes_dues, org, chaines)
                else:
                    if comptes_ig is None:
                        comptes_ig = meta.comptes_instagram()
                    publier_meta(reseau, langue, lignes_dues, comptes_ig, dossier)
            except (meta.ErreurMeta, buffer.ErreurBuffer, OSError) as e:  # un compte en panne n'arrête pas les autres
                print(f"ERREUR {reseau} {langue} : {e}")
                erreurs += 1
    sys.exit(1 if erreurs else 0)


if __name__ == "__main__":
    main()
