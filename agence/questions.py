"""Questions Oui/Non à Jules par Telegram, et application de sa réponse par un script à choix fermés.

    python -m agence.questions relever                        (script `reponses` : à chaque réveil, et par
                                                               reponses.yml dès que Jules clique)
    python -m agence.questions poser "<question>" --pourquoi "<ce qui s'est passé>" --oui <action> [--non <action>]
                                     [--conseil "<ce qui aide Jules à choisir>"] [--par <agent>]

Une action est `rien`, `pause:<cible>` ou `reprise:<cible>`, avec une cible connue : agent, script, `tout`
ou `chaine:<langue>`, ou `accord:<n>` / `refus:<n>` sur une PR de code du Pilote (agence/accords.py).
Rien d'autre ne peut sortir d'un clic. Questions dans registre/questions.csv
(la dernière ligne d'une question fait foi).

Les clics arrivent au Worker de l'alarme par webhook (alarme/worker.js, demande #46), qui les garde : Telegram
efface un clic non lu en 2 à 3 minutes, bien avant le réveil suivant. relever les lit là, puis les marque lus.
"""
import argparse
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from agence import alarme, organisation, registre, telegram, youtube

GARDE_S = 6 * 3600  # un clic sur une question inconnue plus récente que ça est gardé (registre en retard)
CLIC = re.compile(r"^q:([0-9a-z-]{1,24}):(oui|non)$")
REVEILS_UTC = (5, 11, 17, 23)  # heures UTC du cron de reveil.yml, à la minute 17
LANGUES = {"en": "anglais", "es": "espagnol", "pt": "portugais"}
# Noms tirés de youtube.CHAINES, seule source : une copie à la main avait inversé l'espagnol et le portugais
NOMS_CHAINES = {l: f"{nom} ({LANGUES.get(l, l)})" for l, (nom, _) in youtube.CHAINES.items()}


def cibles_connues():
    return set(organisation.fiches()) | set(organisation.scripts()) | {"tout"} | {f"chaine:{l}" for l in youtube.CHAINES}


def verifier(action):
    """Lève une erreur si l'action n'est pas dans la liste fermée."""
    if action == "rien":
        return
    genre, _, cible = action.partition(":")
    if genre in ("accord", "refus") and cible.isdigit():
        return
    if genre not in ("pause", "reprise") or cible not in cibles_connues():
        raise ValueError(f"Action refusée : {action!r} (rien, pause:<cible>, reprise:<cible>, accord:<n> ou refus:<n>)")


def appliquer(action, raison):
    verifier(action)
    genre, _, cible = action.partition(":")
    if genre in ("accord", "refus"):
        from agence import accords
        (accords.accepter if genre == "accord" else accords.refuser)(int(cible))
    elif action != "rien":
        registre.pause(cible, "jules", raison, action=genre)


def etat_questions(lignes):
    """La dernière ligne de chaque question, par identifiant."""
    etat = {}
    for ligne in lignes:
        etat[ligne["id"]] = ligne
    return etat


def decrire(cible):
    """Une cible en clair, pour Jules."""
    if cible == "tout":
        return "toute l'agence"
    if cible.startswith("chaine:"):
        return f"les envois sur la chaîne {NOMS_CHAINES.get(cible[7:], cible[7:])}"
    fiches, scripts = organisation.fiches(), organisation.scripts()
    if cible in fiches:
        return f"l'agent {fiches[cible].get('titre', cible)}"
    if cible in scripts:
        return f"{scripts[cible].get('description', 'le programme')} ({cible})"
    return cible


def en_clair(action):
    if action == "rien":
        return "rien ne change"
    genre, _, cible = action.partition(":")
    if genre == "accord":
        return f"je fusionne la PR #{cible}, son code tournera au prochain réveil"
    if genre == "refus":
        return f"je ferme la PR #{cible}, le Pilote le verra à sa séance suivante"
    return f"{'je relance' if genre == 'reprise' else 'je mets en pause'} {decrire(cible)}"


def prochain_reveil(maintenant):
    """Heure du prochain réveil prévu, à Paris (GitHub le décale parfois de quelques minutes à quelques heures)."""
    jour = maintenant.replace(minute=17, second=0, microsecond=0)
    for decalage in range(2):
        for heure in REVEILS_UTC:
            quand = jour.replace(hour=heure) + timedelta(days=decalage)
            if quand > maintenant:
                return quand.astimezone(ZoneInfo("Europe/Paris")).strftime("%Hh%M")


def message(texte, pourquoi, si_oui, si_non, par, conseil="", maintenant=None):
    titre = organisation.fiches().get(par, {}).get("titre", par)
    morceaux = [f"Question de l'agent {titre}", texte, f"Pourquoi : {pourquoi}"]
    if conseil:
        morceaux.append(f"Pour t'aider à choisir : {conseil}")
    non = "ça reste en pause" if si_non == "rien" and si_oui.startswith("reprise:") else en_clair(si_non)
    morceaux.append(f"Oui : {en_clair(si_oui)}.\nNon : {non}.")
    morceaux.append("Ta réponse est enregistrée dès le clic (les boutons disparaissent) et appliquée dans les minutes "
                    "qui suivent, au plus tard au prochain réveil de l'agence (prévu vers "
                    f"{prochain_reveil(maintenant or datetime.now(timezone.utc))}, que GitHub peut retarder de "
                    "quelques heures). Ce message changera encore quand ce sera fait.")
    return "\n\n".join(morceaux)


def poser(texte, si_oui, si_non="rien", par="pilote", pourquoi="", conseil=""):
    if not pourquoi:
        raise ValueError("Une question à Jules dit toujours pourquoi elle est posée")
    verifier(si_oui)
    verifier(si_non)
    if si_oui == "rien" and si_non == "rien":
        raise ValueError("Un clic doit changer quelque chose : Oui et Non ne peuvent pas valoir tous deux « rien »")
    ouvertes = etat_questions(registre.lire("questions"))
    base = datetime.now(timezone.utc).strftime("%m%d-%H%M")
    ident = next(f"{base}-{n}" for n in range(1, 100) if f"{base}-{n}" not in ouvertes)
    message_id = telegram.envoyer(message(texte, pourquoi, si_oui, si_non, par, conseil),
                                  [("Oui", f"q:{ident}:oui"), ("Non", f"q:{ident}:non")])
    registre.ajouter("questions", [{"date": registre.maintenant(), "id": ident, "par": par, "texte": texte,
                                    "si_oui": si_oui, "si_non": si_non, "etat": "ouverte", "reponse": "",
                                    "message_id": message_id}])
    registre.decider(par, f"question à Jules : {texte}", f"{pourquoi} Oui = {si_oui}, Non = {si_non}")
    return ident


def clore(si_oui, raison):
    """Ferme les questions ouvertes qui proposaient `si_oui`, devenu inutile (ex. pause levée seule), et le dit à Jules."""
    for q in etat_questions(registre.lire("questions")).values():
        if q["etat"] == "ouverte" and q["si_oui"] == si_oui:
            registre.ajouter("questions", [{**q, "date": registre.maintenant(), "etat": "close", "reponse": ""}])
            try:
                telegram.remplacer(int(q["message_id"]), f"{q['texte']}\n\nPlus besoin de répondre : {raison}")
            except RuntimeError as e:
                print(f"Message non mis à jour : {e}")


def _deja(question, texte):
    """Ce que voit Jules après un clic qui ne change rien (question inconnue, close, ou clic relu)."""
    if not question:
        return f"{texte}\n\nQuestion inconnue de l'agence : rien n'est fait."
    if question["etat"] == "repondue":
        return f"{question['texte']}\n\nTa réponse : {question['reponse'].upper()} (déjà prise)."
    return f"{question['texte']}\n\nPlus besoin de répondre : rien n'est fait."


def relever():
    """Lit les clics de Jules gardés par le Worker, applique la réponse aux questions ouvertes, marque les clics lus.
    Un clic relu (marquage perdu) tombe sur une question déjà répondue : jamais appliqué deux fois.
    Renvoie le nombre de réponses prises."""
    questions, prises, lus = etat_questions(registre.lire("questions")), 0, []
    for clic in alarme.clics_recus():
        trouve = CLIC.match(clic.get("donnee", ""))
        question = questions.get(trouve.group(1)) if trouve else None
        if trouve and not question and time.time() - clic.get("envoi", 0) < GARDE_S:
            # Question récente absente d'ici : ce registre est en retard sur celui qui l'a posée. Le clic reste
            # au Worker pour le prochain passage au lieu d'être perdu.
            print(f"Clic sur {trouve.group(1)}, question pas encore dans ce registre : gardé pour le prochain passage")
            continue
        lus.append(clic["update_id"])
        if not question or question["etat"] != "ouverte":
            _remplacer(clic["message_id"], _deja(question, clic.get("texte", "")))
            continue
        reponse = trouve.group(2)
        action = question["si_oui"] if reponse == "oui" else question["si_non"]
        try:
            appliquer(action, f"réponse {reponse} de Jules à : {question['texte']}")
            fait = f"C'est fait : {en_clair(action)}."
        except RuntimeError as e:  # fusion refusée par GitHub, clé absente : Jules le voit, le clic n'est pas rejoué
            fait = f"Pas pu le faire ({e})."
            print(f"Réponse {reponse} à {question['id']} non appliquée : {e}")
        question = {**question, "date": registre.maintenant(), "etat": "repondue", "reponse": reponse}
        registre.ajouter("questions", [question])
        questions[question["id"]] = question
        prises += 1
        print(f"Réponse {reponse} à {question['id']} : {action}")
        _remplacer(clic["message_id"], f"{question['texte']}\n\nTa réponse : {reponse.upper()}. {fait}")
    if lus:
        alarme.clics_lus(lus)
    return prises


def _remplacer(id_message, texte):
    try:
        telegram.remplacer(int(id_message), texte)
    except RuntimeError as e:  # message identique ou effacé : sans gravité, la réponse est prise
        print(f"Message non mis à jour : {e}")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    sous = p.add_subparsers(dest="commande", required=True)
    sous.add_parser("relever")
    q = sous.add_parser("poser")
    q.add_argument("texte")
    q.add_argument("--pourquoi", required=True)
    q.add_argument("--conseil", default="")
    q.add_argument("--oui", required=True)
    q.add_argument("--non", default="rien")
    q.add_argument("--par", default="pilote")
    args = p.parse_args()
    if args.commande == "poser":
        print(f"Question posée : {poser(args.texte, args.oui, args.non, args.par, args.pourquoi, args.conseil)}")
        return
    with registre.seance("reponses") as info:
        info["resultat"] = f"ok : {relever()} réponse(s) de Jules"
        print(info["resultat"])


if __name__ == "__main__":
    main()
