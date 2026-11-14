"""Contacts avec des humains : un premier message est préparé par l'agence, attend la validation de Jules, puis part.

    python -m agence.lancer contacts    à chaque réveil : envoie les messages validés, ou demande le droit d'envoi
    python -m agence.contacts           affiche les messages en attente de validation

MISSION.md, Gouvernance : un message (reçu ou à envoyer) est préparé par l'agence, adapté à son destinataire, avec
le contexte, et mis en attente dans une issue étiquetée `contact`. Claude pose l'étiquette `valide` après en avoir
parlé avec Jules : seule une pose par le compte de Jules compte. Le message part au réveil suivant, au nom de la
chaîne, signé par l'équipe, jamais sous un faux prénom ni au nom de Jules. Un démarchage groupé est un seul lot :
un modèle et une liste de destinataires, validés en une fois.

L'envoi demande un jeton Gmail à part, `GMAIL_SEND_TOKEN`, qui n'a que le droit `gmail.send` (le Courrier lit la
boîte sans pouvoir écrire, ce script écrit sans pouvoir lire : règle de deux). Tant que ce jeton manque ou n'est pas
accordé, rien ne part et l'agence le demande elle-même au guichet, une seule fois.
"""
import base64
import json
import os
import re
import sys
from email.message import EmailMessage

from agence import guichet, registre

ETIQUETTE = "contact"
VALIDE = "valide"
CLE = "GMAIL_SEND_TOKEN"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
EQUIPES = {"en": "Every Second", "es": "Cada Segundo", "pt": "A Cada Segundo"}
SIGNATURES = {"en": "The Every Second team", "es": "El equipo de Cada Segundo", "pt": "A equipe A Cada Segundo"}
ADRESSE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
LOT_MAX = 20                          # destinataires par lot
ENVOIS_MAX = 20                       # mails par passage, tous lots confondus
INTERDITS = ("jules", "hocq")         # jamais au nom de Jules
TITRE_DEMANDE = "Droit d'envoi Gmail (gmail.send) pour les messages validés"


def _adresses(destinataires):
    liste = [a.strip() for a in (destinataires.split(",") if isinstance(destinataires, str) else destinataires)]
    liste = [a for a in liste if a]
    if not liste or len(liste) > LOT_MAX:
        raise ValueError(f"Un contact a de 1 à {LOT_MAX} destinataires")
    for a in liste:
        if not ADRESSE.match(a):
            raise ValueError(f"Adresse refusée : {a!r}")
    return liste


def signer(message, chaine):
    """Le message, signé par l'équipe de la chaîne. Refuse le nom de Jules."""
    if chaine not in EQUIPES:
        raise ValueError(f"Chaîne inconnue : {chaine!r}")
    message = str(message or "").strip()
    if not message:
        raise ValueError("Message vide")
    if any(mot in message.lower() for mot in INTERDITS):
        raise ValueError("Un message part au nom de la chaîne, jamais au nom de Jules")
    return message if message.endswith(SIGNATURES[chaine]) else f"{message}\n\n{SIGNATURES[chaine]}"


def corps(destinataires, chaine, objet, contexte, message, par):
    """Le texte de l'issue : ce que Jules relit, et ce que le script relira pour envoyer."""
    objet = " ".join(str(objet or "").split())[:150]
    if not objet:
        raise ValueError("Objet vide")
    message = signer(message, chaine)
    if "<<<" in message or ">>>" in message:
        raise ValueError("Le message ne contient pas les marques <<< et >>>")
    return (f"- **À :** {', '.join(_adresses(destinataires))}\n- **Chaîne :** {chaine}\n- **Objet :** {objet}\n"
            f"- **Contexte :** {guichet.sans_mention(contexte, 1500) or 'aucun'}\n\n**Message :**\n<<<\n{message}\n>>>\n\n"
            f"_Préparé par {guichet.sans_mention(par, 60)}. Il part au réveil qui suit la pose de l'étiquette "
            f"`{VALIDE}` par Jules. Modifiable ici avant validation._")


def lire(texte):
    """Relit une issue de contact : {destinataires, chaine, objet, message}. Lève ValueError si le format est cassé."""
    champ = lambda nom: re.search(rf"^- \*\*{nom} :\*\* (.+)$", texte, re.MULTILINE)
    a, chaine, objet = champ("À"), champ("Chaîne"), champ("Objet")
    message = re.search(r"^<<<\r?\n(.*?)\r?\n>>>\s*$", texte, re.MULTILINE | re.DOTALL)
    if not (a and chaine and objet and message):
        raise ValueError("format de contact illisible (À, Chaîne, Objet, message entre <<< et >>>)")
    return {"destinataires": _adresses(a.group(1)), "chaine": chaine.group(1).strip(),
            "objet": objet.group(1).strip(), "message": signer(message.group(1), chaine.group(1).strip())}


def preparer(destinataires, chaine, objet, message, contexte, par, gh=None):
    """Met un message en attente de validation. Renvoie le numéro de l'issue, ou None en essai. Rien ne part."""
    gh = gh or guichet._gh
    texte = corps(destinataires, chaine, objet, contexte, message, par)
    titre = guichet.sans_mention(f"Contact ({EQUIPES[chaine]}) : {objet}", 120)
    if os.environ.get("AGENCE_ESSAI") == "1":
        print(f"ESSAI : contact non mis en attente : {titre}\n{texte}")
        return None
    lien = gh("issue", "create", "-R", guichet.DEPOT, "--title", titre, "--label", ETIQUETTE, "--body-file", "-",
              entree=texte)
    numero = int(lien.strip().rsplit("/", 1)[-1])
    registre.decider(par, f"contact #{numero} mis en attente de validation : {titre}",
                     guichet.sans_mention(contexte, 300) or "premier message, à valider par Jules")
    return numero


def _contacts(gh=None):
    return [c for c in guichet._issues(ETIQUETTE, gh=gh) if not c["pr"]]


def en_attente(gh=None):
    """Messages préparés, pas encore validés."""
    return [c for c in _contacts(gh) if VALIDE not in c["etiquettes"]]


def valide_par_jules(evenements):
    """evenements : [(labeled|unlabeled, étiquette, auteur)] dans l'ordre. Vrai si le dernier geste sur `valide` est
    sa pose par le compte de Jules : une étiquette posée par un agent ou un robot ne vaut rien."""
    gestes = [(e, auteur) for e, nom, auteur in evenements if nom == VALIDE]
    return bool(gestes) and gestes[-1] == ("labeled", guichet.JULES)


def _evenements(numero, gh):
    sortie = gh("api", "--paginate", f"repos/{guichet.DEPOT}/issues/{numero}/events?per_page=100", "--jq",
                '.[] | select(.event == "labeled" or .event == "unlabeled") | [.event, .label.name, .actor.login] | @tsv')
    return [tuple(l.split("\t")) for l in sortie.splitlines() if l.strip()]


def valides(gh=None):
    gh = gh or guichet._gh
    return [c for c in _contacts(gh) if VALIDE in c["etiquettes"] and valide_par_jules(_evenements(c["numero"], gh))]


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_info(json.loads(os.environ[CLE].lstrip("﻿")), [SCOPE])
    creds.refresh(Request())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def mail(destinataire, contact):
    m = EmailMessage()
    m["To"] = destinataire
    m["Subject"] = contact["objet"]
    m.set_content(contact["message"])
    return {"raw": base64.urlsafe_b64encode(m.as_bytes()).decode()}


def demander_envoi(gh=None):
    """L'agence demande elle-même le droit d'envoi au guichet (une seule fois, même titre)."""
    return guichet.demander(
        TITRE_DEMANDE,
        quoi=f"Créer pour la boîte boite-chaines un jeton Google qui n'a que le droit `gmail.send` (ni lecture ni "
             f"suppression), le poser en secret `{CLE}` du dépôt agence, et ajouter la ligne "
             f"`{CLE} = [\"contacts\"]` dans `organisation/autorisations.toml`. L'étape Contacts du réveil le lit déjà",
        pourquoi="La Gouvernance prévoit qu'un message validé par Jules parte au réveil suivant. Le jeton Gmail "
                 "actuel (`GMAIL_TOKEN`) ne donne que la lecture et les filtres : sans ce droit, un message validé "
                 "reste en attente et aucune réponse à une collaboration ne part",
        debloque="L'envoi des messages `contact` validés (réponse à une proposition de collaboration, démarchage "
                 "par lot), au nom de la chaîne et signés par l'équipe. Le jeton de lecture du Courrier ne change pas",
        par="contacts", lien="https://developers.google.com/workspace/gmail/api/auth/scopes", cout="0 €", gh=gh)


def passage(gh=None, service=None, cle=None):
    """Un passage : envoie les messages validés si le droit d'envoi est là, sinon le demande au guichet.
    Renvoie le résumé du passage."""
    gh = gh or guichet._gh
    cle = os.environ.get(CLE) if cle is None else cle
    prets = valides(gh)
    if not cle:
        numero, nouvelle = demander_envoi(gh)
        return (f"ok : droit d'envoi absent, demande au guichet #{numero} ({'écrite' if nouvelle else 'déjà faite'}), "
                f"{len(prets)} message(s) validé(s) en attente, rien n'est parti")
    if not prets:
        return "ok : aucun message validé à envoyer"
    service, envoyes, erreurs = service or _service(), 0, []
    for c in prets:
        try:
            contact = lire(c["texte"])
            if envoyes + len(contact["destinataires"]) > ENVOIS_MAX:
                continue   # au réveil suivant : on ne coupe pas un lot en deux
            for destinataire in contact["destinataires"]:
                service.users().messages().send(userId="me", body=mail(destinataire, contact)).execute()
                envoyes += 1
        except Exception as e:   # un message qui échoue ne bloque pas les autres
            # La validation est retirée : sans ça, un lot à moitié parti serait renvoyé en entier au réveil suivant
            erreurs.append(f"#{c['numero']} : {type(e).__name__}: {e}"[:200])
            gh("issue", "edit", str(c["numero"]), "-R", guichet.DEPOT, "--remove-label", VALIDE)
            gh("issue", "comment", str(c["numero"]), "-R", guichet.DEPOT, "--body-file", "-",
               entree=f"Envoi interrompu : {guichet.sans_mention(e, 300)}. Étiquette `{VALIDE}` retirée pour ne rien "
                      f"renvoyer deux fois : à revalider après vérification de ce qui est déjà parti.")
            continue
        with open(registre.DOSSIER / "contacts.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps({"date": registre.maintenant(), "issue": c["numero"], "chaine": contact["chaine"],
                                "objet": contact["objet"], "destinataires": len(contact["destinataires"]),
                                "domaines": sorted({a.split("@")[1] for a in contact["destinataires"]})},
                               ensure_ascii=False) + "\n")
        gh("issue", "comment", str(c["numero"]), "-R", guichet.DEPOT, "--body-file", "-",
           entree=f"Envoyé à {len(contact['destinataires'])} destinataire(s), au nom de {EQUIPES[contact['chaine']]}.")
        gh("issue", "close", str(c["numero"]), "-R", guichet.DEPOT)
        registre.decider("contacts", f"contact #{c['numero']} envoyé ({len(contact['destinataires'])} destinataire(s))",
                         "validé par Jules (étiquette valide posée par son compte)")
    if erreurs:
        raise RuntimeError(f"{envoyes} mail(s) envoyé(s), {len(erreurs)} message(s) en échec : {' ; '.join(erreurs)}")
    return f"ok : {envoyes} mail(s) envoyé(s) pour {len(prets)} message(s) validé(s)"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if "envoyer" not in sys.argv[1:]:
        attente = en_attente()
        print("\n".join(f"#{c['numero']} {c['titre']} {c['lien']}" for c in attente) or "Aucun message en attente.")
        return
    with registre.seance("contacts") as info:
        info["resultat"] = passage()[:200]
        print(info["resultat"])


if __name__ == "__main__":
    main()
