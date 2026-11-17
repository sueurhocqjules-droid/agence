"""Alarme hors de GitHub (sous-étape 17) : le réveil envoie un signe de vie à un Worker Cloudflare,
qui prévient Jules sur Telegram si plus rien n'arrive pendant DELAI_MINUTES (voir alarme/worker.js).

    python -m agence.alarme signe                  # depuis le réveil : rien si ALARME_SECRET manque, jamais d'échec
    python -m agence.alarme deployer [--essai N]   # en local : Worker, KV, secrets, cron (CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID)
    python -m agence.alarme etat                   # en local : état lu dans le KV du Worker
    python -m agence.alarme poser-secret-github    # Jules, une fois : pose ALARME_SECRET sur GitHub sans l'afficher
    python -m agence.alarme brancher-telegram      # en local, après deployer : Telegram pousse les clics au Worker

Le Worker garde aussi les clics de Jules sur les boutons Oui/Non (demande #46) : clics_recus et clics_lus les lisent
pour agence/questions.py, avec le même secret que le signe de vie.

Le secret partagé vit dans .secrets/alarme_secret (ignoré par Git), le Worker et GitHub en ont chacun une copie.
Le secret du webhook Telegram vit dans .secrets/telegram_webhook (le Worker et Telegram en ont une copie). Le jeton
GITHUB_RELANCE_TOKEN (agence/.env, Actions en écriture sur agence seul) est facultatif : sans lui, un clic s'applique
au prochain réveil au lieu de tout de suite.
Le signe de vie transmet aussi les heures du réveil (organisation/rythme.toml, [reveil] heures_utc) : le Worker
lance reveil.yml à chacune d'elles, car le cron de GitHub en sautait environ la moitié et retardait les autres.
Délai normal : 24 h, une journée entière sans aucun réveil malgré le Worker et le cron de GitHub en filet.
"""
import json
import os
import secrets
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
import uuid
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
SOURCE = RACINE / "alarme" / "worker.js"
FICHIER_SECRET = RACINE / ".secrets" / "alarme_secret"
FICHIER_WEBHOOK = RACINE / ".secrets" / "telegram_webhook"
NOM = "agence-alarme"
KV = "agence-alarme-etat"
DEPOT = "sueurhocqjules-droid/agence"
DELAI_MINUTES = 24 * 60
CRON = "7 * * * *"            # toutes les heures : l'alarme part au plus 1 h après le délai
CRON_ESSAI = "* * * * *"
SOUS_DOMAINE = "everysecondlab"   # sous-domaine workers.dev du compte, créé au premier déploiement s'il manque
BASE = f"https://{NOM}.{SOUS_DOMAINE}.workers.dev"   # deployer prévient si l'adresse réelle diffère
ADRESSE = f"{BASE}/signe"
API = "https://api.cloudflare.com/client/v4"
RYTHME = RACINE / "organisation" / "rythme.toml"


# --- Côté réveil -------------------------------------------------------------------------------------------

def heures_reveil(fichier=RYTHME):
    """Heures UTC du réveil choisies par l'agence, ou None si absentes ou invalides (le Worker garde alors les siennes)."""
    try:
        with open(fichier, "rb") as f:
            heures = tomllib.load(f).get("reveil", {}).get("heures_utc")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    if not isinstance(heures, list) or not 0 < len(heures) <= 24:
        return None
    if not all(isinstance(h, int) and not isinstance(h, bool) and 0 <= h <= 23 for h in heures):
        return None
    return sorted(set(heures))


def signe(source="réveil", adresse=None, ouvrir=urllib.request.urlopen, heures=None):
    """Envoie un signe de vie (et les heures du réveil). Ne lève jamais : un échec se voit à l'alarme, pas en cassant le réveil."""
    secret = os.environ.get("ALARME_SECRET", "").strip()
    if not secret:
        print("Signe de vie non envoyé : ALARME_SECRET n'est pas posé sur GitHub (python -m agence.alarme poser-secret-github)")
        return False
    corps = {"source": source}
    heures = heures if heures is not None else heures_reveil()
    if heures:
        corps["heures_utc"] = heures
    requete = urllib.request.Request(adresse or ADRESSE, data=json.dumps(corps).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json",
                                              "User-Agent": "agence-reveil"})
    try:
        with ouvrir(requete, timeout=20) as reponse:
            print(f"Signe de vie reçu par l'alarme : {json.load(reponse).get('dernier')}")
            return True
    except urllib.error.HTTPError as e:
        print(f"Signe de vie refusé par l'alarme : {e.code}")
    except (urllib.error.URLError, OSError, ValueError) as e:
        print(f"Alarme injoignable : {e}")
    return False


# --- Clics de Jules gardés par le Worker (agence/questions.py) -----------------------------------------------

def _secret_alarme():
    secret = os.environ.get("ALARME_SECRET", "").strip()
    if not secret and FICHIER_SECRET.exists():
        secret = FICHIER_SECRET.read_text(encoding="utf-8").strip()
    if not secret:
        raise RuntimeError("ALARME_SECRET manquant : les clics de Jules ne peuvent pas être lus")
    return secret


def _worker(methode, chemin, donnees=None, ouvrir=urllib.request.urlopen):
    corps = json.dumps(donnees).encode() if donnees is not None else None
    requete = urllib.request.Request(f"{BASE}{chemin}", data=corps, method=methode,
                                     headers={"Authorization": f"Bearer {_secret_alarme()}",
                                              "Content-Type": "application/json", "User-Agent": "agence-reponses"})
    try:
        with ouvrir(requete, timeout=30) as reponse:
            return json.load(reponse)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Worker {methode} {chemin} : {e.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise RuntimeError(f"Worker injoignable ({chemin}) : {e}") from None


def clics_recus(ouvrir=urllib.request.urlopen):
    """Clics gardés par le Worker, du plus ancien au plus récent : dicts update_id, clic_id, donnee, message_id,
    envoi (date du message, en secondes), texte (texte du message au moment du clic), recu."""
    return sorted(_worker("GET", "/clics", ouvrir=ouvrir)["clics"], key=lambda c: c["update_id"])


def clics_lus(ids, ouvrir=urllib.request.urlopen):
    """Retire du Worker les clics traités."""
    return _worker("POST", "/clics/lus", {"ids": sorted(ids)}, ouvrir=ouvrir)


# --- Côté Cloudflare (en local) ----------------------------------------------------------------------------

def _cloudflare(methode, chemin, donnees=None, corps=None, type_contenu="application/json"):
    jeton, compte = os.environ["CLOUDFLARE_API_TOKEN"], os.environ["CLOUDFLARE_ACCOUNT_ID"]
    if donnees is not None:
        corps = json.dumps(donnees).encode()
    requete = urllib.request.Request(f"{API}/accounts/{compte}{chemin}", data=corps, method=methode,
                                     headers={"Authorization": f"Bearer {jeton}", "Content-Type": type_contenu})
    try:
        with urllib.request.urlopen(requete, timeout=60) as reponse:
            brut = reponse.read()
    except urllib.error.HTTPError as e:
        brut = e.read()
        try:
            erreurs = json.loads(brut).get("errors")
        except ValueError:
            erreurs = brut[:300]
        raise RuntimeError(f"Cloudflare {methode} {chemin} : {e.code} {erreurs}") from None
    try:
        resultat = json.loads(brut)
    except ValueError:
        return brut   # valeur brute du KV
    if isinstance(resultat, dict) and "success" in resultat:
        if not resultat["success"]:
            raise RuntimeError(f"Cloudflare {methode} {chemin} : {resultat.get('errors')}")
        return resultat.get("result")
    return resultat


def _secret_local(fichier):
    """Un secret créé au premier déploiement dans .secrets/ (ignoré par Git), jamais affiché. token_urlsafe ne
    donne que A-Z, a-z, 0-9, _ et -, les seuls caractères admis par Telegram pour secret_token."""
    if not fichier.exists():
        fichier.parent.mkdir(exist_ok=True)
        fichier.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return fichier.read_text(encoding="utf-8").strip()


def secret_partage():
    return _secret_local(FICHIER_SECRET)


def secret_webhook():
    return _secret_local(FICHIER_WEBHOOK)


def jeton_relance():
    """GITHUB_RELANCE_TOKEN (environnement ou agence/.env), ou "" s'il n'est pas posé."""
    from agence import telegram   # même lecture de agence/.env que les clés Telegram
    try:
        return telegram._reglage("GITHUB_RELANCE_TOKEN")
    except RuntimeError:
        return ""


def espace_kv():
    for espace in _cloudflare("GET", "/storage/kv/namespaces?per_page=100") or []:
        if espace["title"] == KV:
            return espace["id"]
    return _cloudflare("POST", "/storage/kv/namespaces", {"title": KV})["id"]


def metadonnees(id_kv, delai_minutes, essai, secret, bot, chat, webhook="", relance=""):
    """Liaisons du Worker. Les secrets sont reposés à chaque déploiement, depuis l'environnement et .secrets/."""
    meta = {
        "main_module": "worker.js",
        "compatibility_date": "2026-11-01",
        "bindings": [
            {"type": "kv_namespace", "name": "ETAT", "namespace_id": id_kv},
            {"type": "plain_text", "name": "DELAI_MINUTES", "text": str(delai_minutes)},
            {"type": "plain_text", "name": "ESSAI", "text": "1" if essai else ""},
            {"type": "secret_text", "name": "SIGNE_SECRET", "text": secret},
            {"type": "secret_text", "name": "TELEGRAM_BOT_TOKEN", "text": bot},
            {"type": "secret_text", "name": "TELEGRAM_CHAT_ID", "text": chat},
        ],
    }
    for nom, valeur in (("WEBHOOK_SECRET", webhook), ("GITHUB_RELANCE_TOKEN", relance)):
        if valeur:
            meta["bindings"].append({"type": "secret_text", "name": nom, "text": valeur})
    return meta


def _multipart(meta, source):
    limite = uuid.uuid4().hex
    parties = [
        (f'--{limite}\r\nContent-Disposition: form-data; name="metadata"\r\nContent-Type: application/json\r\n\r\n'
         ).encode() + json.dumps(meta).encode() + b"\r\n",
        (f'--{limite}\r\nContent-Disposition: form-data; name="worker.js"; filename="worker.js"\r\n'
         f'Content-Type: application/javascript+module\r\n\r\n').encode() + source + b"\r\n",
        f"--{limite}--\r\n".encode(),
    ]
    return b"".join(parties), f"multipart/form-data; boundary={limite}"


def sous_domaine_compte():
    """Le sous-domaine workers.dev du compte, créé (nom neutre, pas celui de Jules) s'il n'existe pas encore."""
    try:
        return _cloudflare("GET", "/workers/subdomain")["subdomain"]
    except RuntimeError:
        return _cloudflare("PUT", "/workers/subdomain", {"subdomain": SOUS_DOMAINE})["subdomain"]


def deployer(essai_minutes=None):
    """Déploie (ou redéploie) le Worker. essai_minutes : délai raccourci, cron chaque minute, messages marqués TEST."""
    essai = essai_minutes is not None
    id_kv = espace_kv()
    relance = jeton_relance()
    meta = metadonnees(id_kv, essai_minutes if essai else DELAI_MINUTES, essai, secret_partage(),
                       os.environ["TELEGRAM_BOT_TOKEN"], os.environ["TELEGRAM_CHAT_ID"], secret_webhook(), relance)
    corps, type_contenu = _multipart(meta, SOURCE.read_bytes())
    _cloudflare("PUT", f"/workers/scripts/{NOM}", corps=corps, type_contenu=type_contenu)
    sous_domaine = sous_domaine_compte()
    _cloudflare("PUT", f"/workers/scripts/{NOM}/schedules", [{"cron": CRON_ESSAI if essai else CRON}])
    _cloudflare("POST", f"/workers/scripts/{NOM}/subdomain", {"enabled": True, "previews_enabled": False})
    adresse = f"https://{NOM}.{sous_domaine}.workers.dev/signe"
    print(f"Worker {NOM} déployé : délai {meta['bindings'][1]['text']} min, cron {CRON_ESSAI if essai else CRON}, "
          f"{'ESSAI' if essai else 'normal'}, clics appliqués {'tout de suite' if relance else 'au prochain réveil'}")
    if adresse != ADRESSE:
        print(f"ATTENTION : l'adresse réelle est {adresse}, à reporter dans BASE (agence/alarme.py)")
    return adresse


def brancher_telegram():
    """Telegram pousse désormais chaque clic au Worker (un clic non lu disparaît en 2 à 3 minutes chez Telegram).
    Un webhook posé rend getUpdates inutilisable : plus rien ne doit le lire."""
    from agence import telegram
    telegram.appeler("setWebhook", {"url": f"{BASE}/telegram", "secret_token": secret_webhook(),
                                    "allowed_updates": ["callback_query"], "max_connections": 5})
    info = telegram.appeler("getWebhookInfo", {})
    print(f"Webhook Telegram branché sur {info.get('url')} ({info.get('pending_update_count', 0)} clic(s) en attente)")


def etat():
    try:
        valeur = _cloudflare("GET", f"/storage/kv/namespaces/{espace_kv()}/values/etat")
    except RuntimeError as e:
        if " 404 " in str(e):   # aucun signe encore reçu
            return {}
        raise
    return valeur if isinstance(valeur, dict) else json.loads(valeur or b"{}")


def ecrire_etat(valeur):
    _cloudflare("PUT", f"/storage/kv/namespaces/{espace_kv()}/values/etat", corps=json.dumps(valeur).encode(),
                type_contenu="text/plain")


def attendre_alerte(delai_max=600):
    """Pour le test : attend que le cron ait envoyé son message (état avec alerte), sans rien afficher de secret."""
    fin = time.time() + delai_max
    while time.time() < fin:
        courant = etat()
        if courant.get("alerte"):
            return courant
        time.sleep(20)
    return None


def poser_secret_github():
    """Pour Jules : pose ALARME_SECRET sur GitHub depuis .secrets/alarme_secret, valeur passée par l'entrée standard."""
    if not FICHIER_SECRET.exists():
        sys.exit(f"{FICHIER_SECRET} manquant : le secret est créé par python -m agence.alarme deployer")
    subprocess.run(["gh", "secret", "set", "ALARME_SECRET", "-R", DEPOT],
                   input=FICHIER_SECRET.read_text(encoding="utf-8").strip(), text=True, check=True)
    print("ALARME_SECRET posé : le prochain réveil enverra son signe de vie")


def main(arguments):
    commande = arguments[0] if arguments else ""
    if commande == "signe":
        signe(arguments[1] if len(arguments) > 1 else "réveil")
    elif commande == "deployer":
        deployer(int(arguments[2]) if len(arguments) > 2 and arguments[1] == "--essai" else None)
    elif commande == "etat":
        print(json.dumps(etat(), ensure_ascii=False))
    elif commande == "attendre-alerte":
        resultat = attendre_alerte()
        print(json.dumps(resultat, ensure_ascii=False) if resultat else "Aucune alerte dans le délai")
        return 0 if resultat else 1
    elif commande == "mise-en-service":
        ecrire_etat({"dernier": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "source": "mise en service",
                     "alerte": None, "alerte_essai": False})
        print(json.dumps(etat(), ensure_ascii=False))
    elif commande == "poser-secret-github":
        poser_secret_github()
    elif commande == "brancher-telegram":
        brancher_telegram()
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
