"""Guichet : ce que l'agence ne peut pas faire seule (créer un compte, installer un dépôt, poser une clé, ouvrir
une machine, fusionner une PR qui touche un fichier protégé). MISSION.md, Gouvernance.

    python -m agence.lancer guichet     récapitulatif Telegram, une fois par jour, et message immédiat pour l'urgent
    python -m agence.guichet            affiche les demandes ouvertes et les clés déclarées sans autorisation

Seul module qui écrit au guichet. Un agent appelle `demander(...)`, puis continue sur autre chose. Une demande est
une issue du dépôt étiquetée `guichet` (et `urgent` si elle bloque), au format fixe : quoi, pourquoi, lien, ce que
ça débloque, coût. Jules et Claude la traitent dans Jarvis, posent la clé (`gh secret set`) et l'autorisent dans
`organisation/autorisations.toml` ; l'agence la prend au réveil suivant. Une même demande (même titre) ne s'écrit
qu'une fois : fermée par Jules, elle n'est pas rouverte par un agent.
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from agence import organisation, registre, telegram

ETIQUETTE = "guichet"
URGENT = "urgent"
JULES = "sueurhocqjules-droid"
ROBOT = "github-actions[bot]"
AUTEURS = (JULES, ROBOT)              # seules les demandes écrites par l'agence ou par Jules comptent
DEPOT = os.environ.get("GITHUB_REPOSITORY", f"{JULES}/agence")
ETAT = registre.DOSSIER / "guichet.json"
PARIS = ZoneInfo("Europe/Paris")
HEURE_RECAP = 6                       # pas de récapitulatif avant 6 h à Paris (le réveil de 0h17 ne réveille personne)
CHAMPS = ("Quoi", "Pourquoi", "Lien", "Ce que ça débloque", "Coût")


def _gh(*args, entree=None):
    return subprocess.run(["gh", *args], input=entree, capture_output=True, text=True, encoding="utf-8",
                          check=True).stdout


def sans_mention(texte, n):
    """Texte d'un agent ou d'un modèle, sûr dans une issue : sur une ligne, borné, sans mention (@)."""
    return " ".join(str(texte or "").replace("@", "(a)").split())[:n].strip()


def corps(quoi, pourquoi, lien, debloque, cout, par=""):
    """Le format fixe d'une demande. Chaque champ est obligatoire, sauf le lien (« aucun »)."""
    valeurs = (sans_mention(quoi, 1500), sans_mention(pourquoi, 1000), sans_mention(lien, 300) or "aucun",
               sans_mention(debloque, 600), sans_mention(cout, 200))
    for champ, valeur in zip(CHAMPS, valeurs):
        if not valeur:
            raise ValueError(f"Demande au guichet sans « {champ} » : le format est fixe")
    lignes = [f"- **{champ} :** {valeur}" for champ, valeur in zip(CHAMPS, valeurs)]
    return "\n".join(lignes) + (f"\n\n_Demande de {sans_mention(par, 60)}, écrite par l'agence._" if par else "")


def _issues(etiquettes, etat="open", gh=None):
    brut = (gh or _gh)("api", "-X", "GET", f"repos/{DEPOT}/issues", "-f", f"labels={etiquettes}", "-f", f"state={etat}",
                       "-f", "per_page=100")
    return [{"numero": i["number"], "titre": i["title"], "texte": i.get("body") or "", "lien": i["html_url"],
             "date": i["created_at"], "ferme": i.get("closed_at"), "ouverte": i["state"] == "open",
             "etiquettes": [e["name"] for e in i["labels"]], "pr": "pull_request" in i,
             "urgent": URGENT in [e["name"] for e in i["labels"]]}
            for i in json.loads(brut or "[]") if i["user"]["login"] in AUTEURS]


def ouvertes(gh=None):
    """Demandes ouvertes du guichet, issues et PR en attente de Jules, les urgentes d'abord, puis les plus anciennes."""
    return sorted(_issues(ETIQUETTE, gh=gh), key=lambda d: (not d["urgent"], d["date"]))


def toutes(gh=None):
    """Demandes ouvertes et fermées (les 100 dernières) : pour ne pas redemander, et pour compter au bilan."""
    return _issues(ETIQUETTE, etat="all", gh=gh)


def demander(titre, quoi, pourquoi, debloque, par, lien="", cout="0 €", urgent=False, gh=None):
    """Écrit une demande au guichet. Renvoie (numéro, nouvelle) : la demande existante si le même titre a déjà été
    demandé (ouverte ou fermée), et (None, False) en essai. Jules l'apprend par le récapitulatif du jour, tout de
    suite au réveil en cours si `urgent`."""
    gh = gh or _gh
    titre = sans_mention(titre, 120)
    texte = corps(quoi, pourquoi, lien, debloque, cout, par)
    if os.environ.get("AGENCE_ESSAI") == "1":
        print(f"ESSAI : demande au guichet non envoyée : {titre}\n{texte}")
        return None, False
    for d in toutes(gh):
        if not d["pr"] and d["titre"] == titre:
            print(f"Guichet : déjà demandé (#{d['numero']}, {'ouverte' if d['ouverte'] else 'fermée'}) : {titre}")
            return d["numero"], False
    etiquettes = ETIQUETTE + (f",{URGENT}" if urgent else "")
    lien_issue = gh("issue", "create", "-R", DEPOT, "--title", titre, "--label", etiquettes, "--body-file", "-",
                    entree=texte)
    numero = int(lien_issue.strip().rsplit("/", 1)[-1])
    registre.decider(par, f"demande au guichet #{numero} : {titre}", sans_mention(pourquoi, 300))
    print(f"Guichet : demande #{numero} écrite : {titre}")
    return numero, True


def signaler_pr(pr, quoi, pourquoi, debloque, lien, cout="0 €", detail="", gh=None):
    """Une PR qui attend Jules (fichier protégé) arrive au guichet : étiquette et commentaire au format fixe."""
    gh = gh or _gh
    gh("pr", "edit", str(pr), "-R", DEPOT, "--add-label", ETIQUETTE)
    gh("pr", "comment", str(pr), "-R", DEPOT, "--body-file", "-",
       entree=f"**Demande au guichet**\n\n{corps(quoi, pourquoi, lien, debloque, cout)}"
              + (f"\n\n{detail}" if detail else ""))


# --- Clés --------------------------------------------------------------------------------------------------------

def cles_sans_autorisation():
    """[(clé, poste ou script)] : clés déclarées par une fiche ou un script, mais pas (encore) accordées par Jules
    dans organisation/autorisations.toml. Le lanceur ne les transmet pas."""
    manquantes = []
    declarees = {nom: fiche.get("env", []) for nom, fiche in organisation.fiches().items()}
    declarees |= {nom: s.get("secrets", []) for nom, s in organisation.scripts().items()}
    for nom, cles in sorted(declarees.items()):
        accordees, _ = organisation.cles_accordees(nom, cles)
        manquantes += [(cle, nom) for cle in cles if cle not in accordees]
    return manquantes


# --- Récapitulatif -----------------------------------------------------------------------------------------------

def _ligne(d):
    return f"{'URGENT ' if d['urgent'] else ''}#{d['numero']} {d['titre']}\n{d['lien']}"


def message_recap(demandes, contacts, cles):
    """Le récapitulatif du jour, ou None s'il n'y a rien à dire."""
    morceaux = []
    if demandes:
        morceaux.append(f"Guichet : {len(demandes)} demande(s) ouverte(s)\n" + "\n".join(_ligne(d) for d in demandes))
    if contacts:
        morceaux.append(f"Contacts : {len(contacts)} message(s) à valider\n"
                        + "\n".join(f"#{c['numero']} {c['titre']}\n{c['lien']}" for c in contacts))
    if cles:
        morceaux.append("Clés déclarées sans ton accord (non transmises) : "
                        + ", ".join(f"{cle} pour {nom}" for cle, nom in cles))
    if not morceaux:
        return None
    return "\n\n".join(["Récapitulatif du guichet", *morceaux,
                        "Rien ne presse sauf ce qui est marqué URGENT : l'agence continue sur autre chose."])


def passage(maintenant, etat, demandes, contacts, cles, envoyer):
    """Un passage du guichet. Message immédiat pour une demande urgente pas encore signalée, récapitulatif une fois
    par jour (premier réveil après 6 h à Paris). Renvoie (nouvel état, ce qui a été envoyé)."""
    etat = {"recap": etat.get("recap", ""), "urgents": list(etat.get("urgents", []))}
    envoyes = []
    ouverts = {d["numero"] for d in demandes}
    for d in demandes:
        if d["urgent"] and d["numero"] not in etat["urgents"]:
            envoyer(f"Demande urgente au guichet\n{_ligne(d)}\n\n{d['texte'][:1500]}")
            etat["urgents"].append(d["numero"])
            envoyes.append(f"urgent #{d['numero']}")
    etat["urgents"] = [n for n in etat["urgents"] if n in ouverts]
    ici = maintenant.astimezone(PARIS)
    if ici.hour >= HEURE_RECAP and etat["recap"] != f"{ici:%Y-%m-%d}":
        texte = message_recap(demandes, contacts, cles)
        if texte:
            envoyer(texte)
            envoyes.append("récapitulatif")
        etat["recap"] = f"{ici:%Y-%m-%d}"
    return etat, envoyes


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    from agence import contacts   # ici seulement : contacts importe ce module
    demandes, attente, cles = ouvertes(), contacts.en_attente(), cles_sans_autorisation()
    if "recap" not in sys.argv[1:]:
        print(message_recap(demandes, attente, cles) or "Guichet : rien d'ouvert.")
        return
    with registre.seance("guichet") as info:
        etat = json.loads(ETAT.read_text(encoding="utf-8")) if ETAT.exists() else {}
        etat, envoyes = passage(datetime.now(timezone.utc), etat, demandes, attente, cles, telegram.envoyer)
        ETAT.write_text(json.dumps(etat, ensure_ascii=False) + "\n", encoding="utf-8")
        info["resultat"] = (f"ok : {len(demandes)} demande(s) ouverte(s), {len(attente)} contact(s) à valider, "
                            f"envoyé : {', '.join(envoyes) or 'rien'}")
        print(info["resultat"])


if __name__ == "__main__":
    main()
