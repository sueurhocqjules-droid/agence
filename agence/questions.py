"""Questions Oui/Non à Jules par Telegram, et application de sa réponse par un script à choix fermés.

    python -m agence.questions relever                        (script `reponses`, à chaque réveil)
    python -m agence.questions poser "<texte>" --oui <action> [--non <action>] [--par <agent>]

Une action est `rien`, `pause:<cible>` ou `reprise:<cible>`, avec une cible connue : agent, script, `tout`
ou `chaine:<langue>`. Rien d'autre ne peut sortir d'un clic. Questions dans registre/questions.csv
(la dernière ligne d'une question fait foi), décalage Telegram dans registre/telegram.json.
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone

from agence import organisation, registre, telegram, youtube

DECALAGE = registre.DOSSIER / "telegram.json"
CLIC = re.compile(r"^q:([0-9a-z-]{1,24}):(oui|non)$")


def cibles_connues():
    return set(organisation.fiches()) | set(organisation.scripts()) | {"tout"} | {f"chaine:{l}" for l in youtube.CHAINES}


def verifier(action):
    """Lève une erreur si l'action n'est pas dans la liste fermée."""
    if action == "rien":
        return
    genre, _, cible = action.partition(":")
    if genre not in ("pause", "reprise") or cible not in cibles_connues():
        raise ValueError(f"Action refusée : {action!r} (rien, pause:<cible> ou reprise:<cible>)")


def appliquer(action, raison):
    verifier(action)
    if action != "rien":
        genre, _, cible = action.partition(":")
        registre.pause(cible, "jules", raison, action=genre)


def etat_questions(lignes):
    """La dernière ligne de chaque question, par identifiant."""
    etat = {}
    for ligne in lignes:
        etat[ligne["id"]] = ligne
    return etat


def poser(texte, si_oui, si_non="rien", par="direction"):
    verifier(si_oui)
    verifier(si_non)
    ouvertes = etat_questions(registre.lire("questions"))
    base = datetime.now(timezone.utc).strftime("%m%d-%H%M")
    ident = next(f"{base}-{n}" for n in range(1, 100) if f"{base}-{n}" not in ouvertes)
    message = telegram.envoyer(f"Question de l'agence ({par})\n\n{texte}\n\nOui : {si_oui}\nNon : {si_non}",
                               [("Oui", f"q:{ident}:oui"), ("Non", f"q:{ident}:non")])
    registre.ajouter("questions", [{"date": registre.maintenant(), "id": ident, "par": par, "texte": texte,
                                    "si_oui": si_oui, "si_non": si_non, "etat": "ouverte", "reponse": "",
                                    "message_id": message}])
    registre.decider(par, f"question à Jules : {texte}", f"Oui = {si_oui}, Non = {si_non}")
    return ident


def relever():
    """Lit les clics de Jules, applique la réponse aux questions ouvertes. Renvoie le nombre de réponses prises."""
    depuis = json.loads(DECALAGE.read_text(encoding="utf-8"))["decalage"] if DECALAGE.exists() else 0
    prochain, clics = telegram.clics(depuis)
    questions, prises = etat_questions(registre.lire("questions")), 0
    for id_clic, donnee, id_message in clics:
        trouve = CLIC.match(donnee)
        question = questions.get(trouve.group(1)) if trouve else None
        if not question or question["etat"] != "ouverte":
            _accuser(id_clic, "Question inconnue ou déjà tranchée")
            continue
        reponse = trouve.group(2)
        action = question["si_oui"] if reponse == "oui" else question["si_non"]
        appliquer(action, f"réponse {reponse} de Jules à : {question['texte']}")
        question = {**question, "date": registre.maintenant(), "etat": "repondue", "reponse": reponse}
        registre.ajouter("questions", [question])
        questions[question["id"]] = question
        prises += 1
        print(f"Réponse {reponse} à {question['id']} : {action}")
        _accuser(id_clic, f"Bien reçu : {reponse}")
        try:
            telegram.remplacer(int(id_message), f"{question['texte']}\n\nTa réponse : {reponse.upper()}. Appliqué : {action}")
        except RuntimeError as e:
            print(f"Message non mis à jour : {e}")
    DECALAGE.write_text(json.dumps({"decalage": prochain}) + "\n", encoding="utf-8")
    return prises


def _accuser(id_clic, texte):
    try:
        telegram.accuser(id_clic, texte)
    except RuntimeError:
        pass  # un clic de plus de quelques minutes ne peut plus être accusé : sans gravité


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("relever")
    q = sous.add_parser("poser")
    q.add_argument("texte")
    q.add_argument("--oui", required=True)
    q.add_argument("--non", default="rien")
    q.add_argument("--par", default="direction")
    args = p.parse_args()
    if args.commande == "poser":
        print(f"Question posée : {poser(args.texte, args.oui, args.non, args.par)}")
        return
    with registre.seance("reponses") as info:
        info["resultat"] = f"ok : {relever()} réponse(s) de Jules"
        print(info["resultat"])


if __name__ == "__main__":
    main()
