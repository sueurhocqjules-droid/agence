"""Accès à l'API de Buffer (GraphQL, https://api.buffer.com) : publication TikTok de l'agence.

Pourquoi Buffer : notre propre appli TikTok publie en privé sans audit, et l'audit refuse un outil interne. Buffer, déjà
audité, publie en public sur nos comptes (test réussi le 13/11, voir a-reverifier.md de Jarvis).
Offre Free (compte prod.hack05) : 3 chaînes, 10 posts en file par chaîne, 25 posts TikTok par 24 h,
API 150 appels par 15 min et 600 par jour. TikTok par Buffer : 3 s à 10 min, 2 200 caractères, 5 hashtags au plus.
Clé : BUFFER_API_KEY (secret GitHub d'agence), sinon le .env de Jarvis. Elle n'apparaît jamais dans un message d'erreur.
Organisation et chaînes sont lues dans Buffer à chaque passage, jamais écrites en dur : une chaîne absente est sautée.
Docs : developers.buffer.com (guides/your-first-post, guides/posts-and-scheduling, reference).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.buffer.com"
JARVIS_ENV = Path(__file__).resolve().parents[2] / "jarvis-starter-kit" / ".env"
TIKTOK = {"en": "everysecondlab", "es": "cadasegundolab", "pt": "acadasegundolab"}  # comptes de l'agence, par langue
LEGENDE_MAX = 2200
HASHTAGS_MAX = 5
FILE_MAX = 10                 # posts en attente par chaîne sur l'offre Free : jamais au-delà
DUREE_MIN_S, DUREE_MAX_S = 3, 600
FINIS = {"sent", "error"}     # statuts d'un post qui ne bougeront plus


class ErreurBuffer(RuntimeError):
    pass


def jeton():
    brut = os.environ.get("BUFFER_API_KEY")
    if not brut and JARVIS_ENV.exists():
        for ligne in JARVIS_ENV.read_text(encoding="utf-8-sig").splitlines():
            nom, sep, valeur = ligne.partition("=")
            if sep and nom.strip() == "BUFFER_API_KEY":
                brut = valeur.strip().strip('"')
    return brut or None


def appel(requete, variables=None):
    corps = json.dumps({"query": requete, "variables": variables or {}}).encode()
    entetes = {"Content-Type": "application/json", "Authorization": f"Bearer {jeton()}",
               "User-Agent": "agence-flux/1.0"}  # un client sans User-Agent peut être refusé par un pare-feu
    try:
        with urllib.request.urlopen(urllib.request.Request(API, data=corps, headers=entetes, method="POST"),
                                    timeout=120) as r:
            reponse = json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            erreurs = json.loads(e.read()).get("errors") or []
        except Exception:  # corps vide, illisible ou pas du JSON : le code HTTP suffit
            erreurs = []
        detail = "; ".join(x.get("message", "?") for x in erreurs) or e.reason
        raise ErreurBuffer(f"HTTP {e.code} : {detail}"[:300]) from None
    except urllib.error.URLError as e:
        raise ErreurBuffer(f"réseau : {e.reason}") from None
    if reponse.get("errors"):
        raise ErreurBuffer("; ".join(x.get("message", "?") for x in reponse["errors"])[:300])
    return reponse.get("data") or {}


def organisation():
    """Id de l'organisation Buffer du compte (une seule sur l'offre Free)."""
    organisations = appel("query { account { organizations { id } } }")["account"]["organizations"]
    if not organisations:
        raise ErreurBuffer("aucune organisation sur le compte Buffer")
    return organisations[0]["id"]


def chaines_tiktok(org):
    """{langue: id de chaîne} des comptes TikTok de l'agence branchés sur Buffer. Absent ou débranché : manque."""
    chaines = appel("query { channels(input: {organizationId: %s}) { id name service isDisconnected } }"
                    % json.dumps(org))["channels"]
    par_nom = {c["name"].lower().lstrip("@"): c["id"] for c in chaines
               if str(c.get("service", "")).lower() == "tiktok" and not c.get("isDisconnected")}
    return {langue: par_nom[nom] for langue, nom in TIKTOK.items() if nom in par_nom}


def posts(org, chaine, maximum=300):
    """Posts d'une chaîne, le plus récent d'abord (pages de 50)."""
    lignes, apres = [], None
    while len(lignes) < maximum:
        requete = ("query { posts(first: 50%s, input: {organizationId: %s, filter: {channelIds: [%s]}, "
                   "sort: [{field: createdAt, direction: desc}]}) { edges { node { id status text externalLink "
                   "error { message } } } pageInfo { hasNextPage endCursor } } }"
                   % (f", after: {json.dumps(apres)}" if apres else "", json.dumps(org), json.dumps(chaine)))
        page = appel(requete)["posts"]
        lignes += [e["node"] for e in page["edges"]]
        if not page.get("pageInfo", {}).get("hasNextPage"):
            break
        apres = page["pageInfo"]["endCursor"]
    return lignes[:maximum]


def statut(post):
    return str(post.get("status") or "").lower()


def titres(lignes):
    """Premières lignes des posts envoyés ou en route (un post en erreur n'a rien publié) : le titre de chaque vidéo."""
    return {(p.get("text") or "").split("\n")[0].strip() for p in lignes if statut(p) != "error"}


def en_file(lignes):
    """Posts qui occupent encore la file de la chaîne (ni envoyés, ni en erreur)."""
    return sum(1 for p in lignes if statut(p) not in FINIS)


def legende(titre, description):
    """Titre en première ligne, puis la description ; 5 hashtags au plus (les suivants sont retirés), 2 200 caractères."""
    vus = 0

    def garder(m):
        nonlocal vus
        vus += 1
        return m.group(0) if vus <= HASHTAGS_MAX else ""
    texte = re.sub(r"(?<![\w#])#\w+", garder, f"{titre}\n\n{description}")
    texte = re.sub(r"[ \t]{2,}", " ", texte)
    return "\n".join(l.rstrip() for l in texte.split("\n")).strip()[:LEGENDE_MAX]


def publier(chaine, adresse, texte, ia=False):
    """Publie tout de suite une vidéo (adresse publique) sur une chaîne TikTok. Renvoie l'id du post Buffer.
    ia : vrai si la vidéo montre des personnes ou des scènes réalistes générées par IA (règle TikTok)."""
    entree = {"channelId": chaine, "schedulingType": "automatic", "mode": "shareNow", "needsApproval": False,
              "text": texte, "assets": [{"video": {"url": adresse, "metadata": {"thumbnailOffset": 2000}}}],
              "metadata": {"tiktok": {"isAiGenerated": bool(ia)}}}
    resultat = appel("mutation Publier($input: CreatePostInput!) { createPost(input: $input) { "
                     "... on PostActionSuccess { post { id status } } ... on MutationError { message } } }",
                     {"input": entree})["createPost"]
    if not resultat.get("post"):
        raise ErreurBuffer(resultat.get("message") or "createPost sans post ni message")
    return resultat["post"]["id"]


def confirmer(org, envoyes, essais=12, pause=20):
    """Relit les posts tout juste créés ({id: chaîne}) jusqu'à ce qu'ils soient envoyés ou en erreur, 4 min au plus.
    Renvoie {id: post} ; un post introuvable ou encore en route garde son dernier état connu."""
    vus = {}
    for i in range(essais):
        for chaine in sorted(set(envoyes.values())):
            for p in posts(org, chaine, maximum=50):
                if p["id"] in envoyes:
                    vus[p["id"]] = p
        if all(statut(vus.get(i_, {})) in FINIS for i_ in envoyes):
            break
        if i < essais - 1:
            time.sleep(pause)
    return vus


def main():
    """python -m agence.buffer : chaînes TikTok branchées et derniers posts, en lecture seule."""
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    if not jeton():
        print("Pas de clé Buffer (BUFFER_API_KEY)")
        sys.exit(1)
    org = organisation()
    for langue, chaine in chaines_tiktok(org).items():
        print(f"TikTok {langue} (@{TIKTOK[langue]}) : chaîne {chaine}")
        for p in posts(org, chaine, maximum=5):
            print(f"  {p['id']} {statut(p)} {(p.get('text') or '').splitlines()[0][:60] if p.get('text') else ''}"
                  f" {p.get('externalLink') or ''} {(p.get('error') or {}).get('message') or ''}".rstrip())


if __name__ == "__main__":
    main()
