"""Accès à l'API Threads : un compte Threads par chaîne, chacun avec son propre jeton.

Branchement, en local, une fois par compte (le compte doit avoir accepté l'invitation de testeur de l'appli
« Every Second Publisher » : profil Threads > Paramètres > Autorisations de sites web > Invitations) :
    python -m agence.threads lien es                          # adresse à ouvrir, connecté au compte Threads de la chaîne
    python -m agence.threads brancher es "<adresse de retour>"  # l'adresse où Threads renvoie, ou son seul code
    python -m agence.threads etat                             # comptes branchés et fin de validité, sans les jetons
Plus simple, sans secret : le générateur de jetons de l'appli (Threads API > Settings > User Token Generator,
compte public seulement), puis le jeton par l'entrée standard :
    python -m agence.threads poser es < fichier_du_jeton
Le code (valable 1 h, une seule fois) s'échange contre un jeton de 60 jours, avec le secret de l'appli
(THREADS_APP_SECRET, .env de Jarvis seulement : le réveil n'en a pas besoin). Les jetons sont rangés chiffrés dans
registre/threads.enc (openssl, clé THREADS_CLE, secret GitHub d'agence et .env de Jarvis) et le réveil les renouvelle
de lui-même (renouveler) : un jeton non renouvelé en 60 jours est perdu, il faut alors rebrancher le compte.
Vidéo : Threads va la chercher à une adresse publique (flux.heberger), 5 min et 1 Go au plus.
Docs : developers.facebook.com/docs/threads/posts et developers.facebook.com/docs/threads/get-started/long-lived-tokens
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HOTE = "https://graph.threads.com/"
GRAPH = HOTE + "v1.0/"
APP_ID = "1159736713405470"   # identifiant Threads de l'appli Meta « Every Second Publisher »
REDIRECTION = "https://agence-alarme.everysecondlab.workers.dev/threads"   # déclarée dans l'appli, à l'identique
PERMISSIONS = "threads_basic,threads_content_publish,threads_manage_insights,threads_read_replies,threads_manage_replies"
COMPTES = {"en": "everysecondlab", "es": "cadasegundolab", "pt": "acadasegundolab"}
FICHIER = Path(__file__).resolve().parents[1] / "registre" / "threads.enc"
JARVIS_ENV = Path(__file__).resolve().parents[2] / "jarvis-starter-kit" / ".env"
TEXTE_MAX_OCTETS = 500          # 500 caractères, un émoji compte pour ses octets UTF-8 : on compte tout en octets
DUREE_MAX_S = 300
RENOUVELER_APRES = timedelta(days=7)   # Threads exige au moins 24 h ; le réveil passe plusieurs fois par jour
PREVENIR_AVANT = timedelta(days=15)    # fin de validité proche : le renouvellement échoue depuis des jours
JETON_GENERE_S = 60 * 24 * 3600        # un jeton du générateur de l'appli vaut 60 jours


class ErreurThreads(RuntimeError):
    pass


def secret(nom):
    """Variable d'environnement, sinon ligne du .env de Jarvis (en local)."""
    brut = os.environ.get(nom)
    if not brut and JARVIS_ENV.exists():
        for ligne in JARVIS_ENV.read_text(encoding="utf-8-sig").splitlines():
            cle, sep, valeur = ligne.partition("=")
            if sep and cle.strip() == nom:
                brut = valeur.strip().strip('"')
    return brut or None


def appel(methode, url, params, jeton=None):
    """Appel à l'API Threads (paramètres en formulaire). Ni le jeton ni le secret n'apparaissent dans une erreur."""
    params = {k: v for k, v in params.items() if v is not None}
    if jeton:
        params["access_token"] = jeton
    url = url if url.startswith("https://") else GRAPH + url
    encode = urllib.parse.urlencode(params)
    if methode == "GET":
        requete = urllib.request.Request(f"{url}?{encode}")
    else:
        requete = urllib.request.Request(url, data=encode.encode(), method=methode)
    try:
        with urllib.request.urlopen(requete, timeout=120) as reponse:
            return json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            erreur = json.loads(e.read()).get("error", {})
        except ValueError:
            erreur = {}
        cible = url.removeprefix(GRAPH).removeprefix(HOTE)
        raise ErreurThreads(f"{methode} {cible} : {erreur.get('message') or e.reason}") from None
    except urllib.error.URLError as e:
        raise ErreurThreads(f"{methode} : réseau injoignable ({e.reason})") from None


# --- Jetons, chiffrés dans le registre -----------------------------------------------------------------------

def _openssl(entree, dechiffrer=False):
    cle = secret("THREADS_CLE")
    if not cle:
        raise ErreurThreads("clé THREADS_CLE absente : jetons Threads illisibles")
    commande = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-iter", "200000", "-a", "-A", "-pass", "env:THREADS_CLE"]
    sortie = subprocess.run(commande + (["-d"] if dechiffrer else ["-salt"]), input=entree, capture_output=True,
                            env={**os.environ, "THREADS_CLE": cle})
    if sortie.returncode:
        raise ErreurThreads("jetons Threads : " + ("déchiffrement refusé (mauvaise clé ?)" if dechiffrer
                                                    else "chiffrement impossible"))
    return sortie.stdout


def lire():
    """{langue: {"id", "nom", "jeton", "obtenu", "expire"}} des comptes branchés, {} si aucun."""
    if not FICHIER.exists():
        return {}
    return json.loads(_openssl(FICHIER.read_bytes().strip(), dechiffrer=True))


def ecrire(comptes):
    FICHIER.write_bytes(_openssl(json.dumps(comptes, sort_keys=True).encode()) + b"\n")


def _fiche(compte, jeton, expire_dans, maintenant):
    return {**compte, "jeton": jeton, "obtenu": maintenant.isoformat(timespec="seconds"),
            "expire": (maintenant + timedelta(seconds=int(expire_dans))).isoformat(timespec="seconds")}


def renouveler(comptes, maintenant):
    """Renouvelle les jetons de plus de RENOUVELER_APRES (60 jours de plus chacun). Renvoie (comptes, problèmes) :
    un problème par compte dont le renouvellement échoue ou dont le jeton expire bientôt. N'écrit rien."""
    comptes, problemes = dict(comptes), []
    for langue, compte in comptes.items():
        if maintenant - datetime.fromisoformat(compte["obtenu"]) >= RENOUVELER_APRES:
            try:
                reponse = appel("GET", HOTE + "refresh_access_token", {"grant_type": "th_refresh_token"},
                                compte["jeton"])
                comptes[langue] = compte = _fiche(compte, reponse["access_token"], reponse["expires_in"], maintenant)
            except ErreurThreads as e:
                problemes.append(f"{langue} : renouvellement du jeton refusé ({e})")
        reste = datetime.fromisoformat(compte["expire"]) - maintenant
        if reste < PREVENIR_AVANT:
            problemes.append(f"{langue} : jeton Threads perdu dans {max(reste.days, 0)} jours, rebrancher le compte "
                             f"(python -m agence.threads lien {langue})")
    return comptes, problemes


# --- Branchement (en local) ----------------------------------------------------------------------------------

def lien(langue):
    return "https://threads.com/oauth/authorize?" + urllib.parse.urlencode({
        "client_id": APP_ID, "redirect_uri": REDIRECTION, "scope": PERMISSIONS, "response_type": "code",
        "state": langue})


def code_de(texte):
    """Le code d'autorisation, depuis l'adresse de retour entière ou le code seul (sans le « #_ » final)."""
    texte = texte.strip()
    if "code=" in texte:
        texte = urllib.parse.parse_qs(urllib.parse.urlsplit(texte).query).get("code", [""])[0]
    return texte.split("#")[0]


def brancher(langue, texte, maintenant=None):
    """Échange le code contre un jeton de 60 jours, vérifie que c'est bien le compte de la chaîne, et le range."""
    maintenant = maintenant or datetime.now(timezone.utc)
    app_secret = secret("THREADS_APP_SECRET")
    if not app_secret:
        raise ErreurThreads("THREADS_APP_SECRET absent du .env de Jarvis")
    court = appel("POST", HOTE + "oauth/access_token", {
        "client_id": APP_ID, "client_secret": app_secret, "grant_type": "authorization_code",
        "redirect_uri": REDIRECTION, "code": code_de(texte)})["access_token"]
    long = appel("GET", HOTE + "access_token", {"grant_type": "th_exchange_token", "client_secret": app_secret}, court)
    return _ranger(langue, long["access_token"], long["expires_in"], maintenant)


def poser(langue, jeton, maintenant=None):
    """Range un jeton de 60 jours déjà fait par le générateur de l'appli (Threads API > Settings > User Token
    Generator, un bouton par testeur) : pas besoin du secret de l'appli."""
    return _ranger(langue, jeton.strip(), JETON_GENERE_S, maintenant or datetime.now(timezone.utc))


def _ranger(langue, jeton, expire_dans, maintenant):
    """Vérifie que le jeton est bien celui du compte de la chaîne, puis le range chiffré."""
    profil = appel("GET", "me", {"fields": "id,username"}, jeton)
    if profil.get("username", "").lower() != COMPTES[langue]:
        raise ErreurThreads(f"jeton de @{profil.get('username')}, attendu @{COMPTES[langue]} : "
                            "prendre celui du bon compte Threads et recommencer")
    comptes = lire()
    comptes[langue] = _fiche({"id": profil["id"], "nom": profil["username"]}, jeton, expire_dans, maintenant)
    ecrire(comptes)
    return comptes[langue]


# --- Publication ---------------------------------------------------------------------------------------------

def legende(titre, description):
    """Titre en première ligne, puis la description. Un seul sujet (#) par post sur Threads : les suivants sont
    retirés. Coupée à 500 octets UTF-8, au dernier blanc."""
    vus = 0

    def garder(m):
        nonlocal vus
        vus += 1
        return m.group(0) if vus == 1 else ""
    texte = re.sub(r"(?<![\w#])#\w+", garder, f"{titre}\n\n{description}")
    texte = "\n".join(re.sub(r"[ \t]{2,}", " ", l).rstrip() for l in texte.split("\n")).strip()
    octets = texte.encode()
    if len(octets) <= TEXTE_MAX_OCTETS:
        return texte
    coupe = octets[:TEXTE_MAX_OCTETS].decode(errors="ignore")
    return coupe[:max(coupe.rfind(" "), coupe.rfind("\n"), len(titre))].rstrip()


def titres(compte, maximum=200):
    """Premières lignes des posts déjà publiés : le titre de chaque vidéo."""
    lignes, apres = [], None
    while len(lignes) < maximum:
        reponse = appel("GET", f"{compte['id']}/threads", {"fields": "text", "limit": 50, "after": apres},
                        compte["jeton"])
        lignes += reponse.get("data", [])
        apres = ((reponse.get("paging") or {}).get("cursors") or {}).get("after")
        if not apres or not (reponse.get("paging") or {}).get("next"):
            break
    return {(p.get("text") or "").split("\n")[0].strip() for p in lignes}


def publier(compte, adresse, titre, description, essais=16, pause=30):
    """Publie une vidéo (adresse publique) sur le compte. Renvoie l'id du post."""
    conteneur = appel("POST", f"{compte['id']}/threads", {
        "media_type": "VIDEO", "video_url": adresse, "text": legende(titre, description),
        "is_carousel_item": "false"}, compte["jeton"])["id"]
    for _ in range(essais):
        time.sleep(pause)   # Threads traite la vidéo avant publication (~30 s conseillées)
        etat = appel("GET", conteneur, {"fields": "status,error_message"}, compte["jeton"])
        if etat.get("status") == "FINISHED":
            return appel("POST", f"{compte['id']}/threads_publish", {"creation_id": conteneur}, compte["jeton"])["id"]
        if etat.get("status") in ("ERROR", "EXPIRED"):
            raise ErreurThreads(f"Threads n'a pas pu traiter la vidéo ({etat.get('error_message') or etat['status']})")
    raise ErreurThreads(f"vidéo toujours en traitement après {essais * pause // 60} min")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    action, *reste = sys.argv[1:] or ["etat"]
    if action == "lien" and reste and reste[0] in COMPTES:
        print(lien(reste[0]))
    elif action == "brancher" and len(reste) == 2 and reste[0] in COMPTES:
        fiche = brancher(reste[0], reste[1])
        print(f"@{fiche['nom']} branché (id {fiche['id']}), jeton valable jusqu'au {fiche['expire'][:10]}")
    elif action == "poser" and len(reste) == 1 and reste[0] in COMPTES:
        fiche = poser(reste[0], sys.stdin.read())   # jeton par l'entrée standard : jamais dans l'historique
        print(f"@{fiche['nom']} branché (id {fiche['id']}), jeton valable jusqu'au {fiche['expire'][:10]}")
    elif action == "etat":
        comptes = lire()
        for langue, nom in COMPTES.items():
            c = comptes.get(langue)
            print(f"{langue} @{nom} : " + (f"branché, jeton valable jusqu'au {c['expire'][:10]}" if c else "pas branché"))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
