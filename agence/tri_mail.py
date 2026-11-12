"""Tri de la boîte de prod.hack05 : une étiquette par chaîne ou adresse en « + », posée par des filtres Gmail.

    python -m agence.tri_mail           crée les filtres manquants (jamais deux fois le même)
    python -m agence.tri_mail --essai   montre ce qui serait créé, ne touche à rien

Droits de Jules (12/11) : lecture et filtres (gmail.readonly, gmail.settings.basic). Créer une étiquette demande
un autre droit (gmail.labels) : les étiquettes de REGLES se créent une fois à la main dans Gmail, le script le dit.
Un filtre ne fait qu'ajouter une étiquette aux mails qui arrivent ensuite : il n'archive, ne lit, ne supprime rien.

REGLES sert aussi au Courrier, qui lit par requête de recherche (requete()) : il ne dépend pas des étiquettes.
"""
import sys

from agence import gmail

PLATEFORMES = "youtube.com OR tiktok.com OR instagram.com OR facebookmail.com OR threads.net OR meta.com"
# (étiquette, critères du filtre Gmail, chaîne de l'agence ou None). Adresses : livrables/business/chaines-escalade/
# 2026-11-10_comptes-reseaux.md (Instagram en « + » par langue, portefeuille Meta en +everysecond).
# TikTok passe par une boîte Outlook (il refuse les « + ») : hors de cette boîte.
REGLES = [
    ("agence/en", {"from": "youtube.com", "query": '"Every Second"'}, "en"),
    ("agence/es", {"to": "prod.hack05+es@gmail.com"}, "es"),
    ("agence/es", {"from": "youtube.com", "query": '"Cada Segundo"', "negatedQuery": '"A Cada Segundo"'}, "es"),
    ("agence/pt", {"to": "prod.hack05+pt@gmail.com"}, "pt"),
    ("agence/pt", {"from": "youtube.com", "query": '"A Cada Segundo"'}, "pt"),
    ("agence/meta", {"to": "prod.hack05+everysecond@gmail.com"}, None),
    ("agence/plateformes", {"from": PLATEFORMES}, None),
]


def requete(criteres):
    """Les critères d'un filtre en requête de recherche Gmail (pour lire sans étiquette)."""
    morceaux = []
    for cle, mot in (("from", "from"), ("to", "to"), ("subject", "subject")):
        if criteres.get(cle):
            morceaux.append(f"{mot}:({criteres[cle]})")
    if criteres.get("query"):
        morceaux.append(f"({criteres['query']})")
    if criteres.get("negatedQuery"):
        morceaux.append(f"-({criteres['negatedQuery']})")
    return " ".join(morceaux)


def normaliser(criteres):
    return tuple(sorted((k, str(v).strip().lower()) for k, v in (criteres or {}).items() if v not in (None, "", False)))


def plan(etiquettes, filtres):
    """Ce qu'il faut faire : (filtres à créer [(étiquette, critères, id)], étiquettes manquantes, déjà en place).

    `etiquettes` : {nom: id} des étiquettes de la boîte ; `filtres` : réponse de filters().list()."""
    existants = {(normaliser(f.get("criteria")), lid) for f in filtres
                 for lid in (f.get("action") or {}).get("addLabelIds", [])}
    a_creer, manquantes, en_place = [], [], 0
    for nom, criteres, _ in REGLES:
        if nom not in etiquettes:
            if nom not in manquantes:
                manquantes.append(nom)
            continue
        if (normaliser(criteres), etiquettes[nom]) in existants:
            en_place += 1
        else:
            a_creer.append((nom, criteres, etiquettes[nom]))
    return a_creer, manquantes, en_place


def lire_boite(service):
    etiquettes = {l["name"]: l["id"] for l in service.users().labels().list(userId="me").execute().get("labels", [])}
    filtres = service.users().settings().filters().list(userId="me").execute().get("filter", [])
    return etiquettes, filtres


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    essai = "--essai" in sys.argv
    service = gmail.service()
    a_creer, manquantes, en_place = plan(*lire_boite(service))
    for nom, criteres, ident in a_creer:
        print(f"{'À CRÉER' if essai else 'CRÉÉ'} : {requete(criteres)} -> {nom}")
        if not essai:
            service.users().settings().filters().create(
                userId="me", body={"criteria": criteres, "action": {"addLabelIds": [ident]}}).execute()
    print(f"{en_place} filtre(s) déjà en place, {len(a_creer)} {'à créer' if essai else 'créé(s)'}")
    if manquantes:
        print("ÉTIQUETTES À CRÉER PAR JULES (Gmail de prod.hack05, Paramètres > Libellés > Créer, une fois), "
              "puis relancer ce script : " + ", ".join(manquantes))
    if not essai and a_creer:  # relecture par l'API : la preuve que les filtres existent
        restant, _, en_place = plan(*lire_boite(service))
        print(f"Relu : {en_place} filtre(s) en place, {len(restant)} manquant(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
