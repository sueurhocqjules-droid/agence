"""Bilan du lundi : une page pour Jules, écrite par script à partir du registre. 0 jeton.

Lancement : python -m agence.lancer bilan   (ou python -m agents.bilan --essai : affiche la page, n'envoie rien)

Un lundi, la page couvre la semaine passée (lundi 0h à lundi 0h UTC). Un autre jour, la semaine en cours.
Ordre fixé par la Gouvernance (MISSION.md, « Canaux ») : à valider, contacts en attente, demandes ouvertes, ce qui a
été fait (organisation comprise), décisions jugées par le Critique, les 4 objectifs en chiffres.
Envoi : une issue du dépôt agence qui mentionne Jules (la mention déclenche le mail de GitHub, le dépôt n'étant pas suivi), un résumé sur Telegram avec le lien,
et une copie dans registre/bilans/. En tête, les sections écrites le dimanche par la Direction et le critique.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from agence import (contacts, delais, guichet, lancer, mesures, questions, registre, suivi_ecarts, telegram,
                    youtube)
from agents import analyste, guetteur, surete

DEPOT = "sueurhocqjules-droid/agence"
PARIS = ZoneInfo("Europe/Paris")
NOMS = questions.NOMS_CHAINES


def periode(maintenant):
    lundi = lancer.debut_semaine(maintenant)
    return (lundi - timedelta(days=7), lundi) if maintenant.weekday() == 0 else (lundi, maintenant)


def quand(texte):
    return datetime.fromisoformat(texte) if texte else None


def chaines(stats, debut, fin):
    """Par chaîne : vidéos sorties dans la période, vues gagnées, vues totales, meilleure vidéo de la période."""
    avant = max((l["releve"] for l in stats if quand(l["releve"]) < debut), default=None)
    apres = max((l["releve"] for l in stats if quand(l["releve"]) < fin), default=None)
    vues_avant = {l["video_id"]: int(l["vues"]) for l in stats if l["releve"] == avant}
    resultat = {}
    for l in (l for l in stats if l["releve"] == apres):
        c = resultat.setdefault(l["chaine"], {"sorties": 0, "gagnees": 0, "total": 0, "meilleure": None})
        gain = int(l["vues"]) - vues_avant.get(l["video_id"], 0)
        c["gagnees"] += gain
        c["total"] += int(l["vues"])
        sortie = quand(l["sortie"])
        if l["statut"] == "public" and sortie and debut <= sortie < fin:
            c["sorties"] += 1
        if gain > 0 and (not c["meilleure"] or gain > c["meilleure"][1]):
            c["meilleure"] = (l["titre"], gain, l["video_id"])
    return resultat, apres, avant


ORDRE = ("1. À valider", "2. Contacts en attente", "3. Demandes ouvertes", "4. Ce qui a été fait",
         "5. Décisions jugées par le Critique", "6. Les 4 objectifs en chiffres")   # MISSION.md, Gouvernance, « Canaux »


def _lire_github(lecture, quoi):
    """Une liste lue sur GitHub (guichet, contacts), ou None si elle est illisible : le bilan part quand même."""
    try:
        return lecture()
    except Exception as e:
        print(f"Bilan : {quoi} illisibles ({type(e).__name__})")
        return None


def _sous_section(lignes):
    """Un bloc écrit avec un titre « ## » passe en « ### » sous l'une des six parties."""
    return [("#" + l) if l.startswith("## ") else l for l in lignes]


def jugees(decisions, debut, fin):
    """Les décisions jugées par le Critique dans la période : (justes, fausses, indéterminées, lignes)."""
    compte, lignes = {"juste": 0, "fausse": 0, "indeterminee": 0}, []
    for d in decisions:
        v = d.get("verdict")
        if v and debut <= quand(v["date"]) < fin:
            compte[v["verdict"]] += 1
            lignes.append(f"- {v['verdict'].capitalize()} : {d['decision'][:140]} ({d['auteur']})"
                          + (f". {v['commentaire'][:160]}" if v.get("commentaire") else ""))
    return compte["juste"], compte["fausse"], compte["indeterminee"], lignes


def organisation_faite(decisions, debut, fin):
    """Ce que l'agence a changé chez elle dans la période : PR fusionnées par l'Ingénierie, postes, demandes."""
    lignes = []
    for d in decisions:
        if not (d.get("date") and debut <= quand(d["date"]) < fin):
            continue
        if d["auteur"] in ("ingenierie", "responsable-organisation") or d["decision"].startswith("demande au guichet"):
            lignes.append(f"- {d['decision'][0].upper() + d['decision'][1:160]} ({d['auteur']})")
    return lignes


def page(maintenant, demandes=None, attente=None, fermees=None):
    """La page du lundi, dans l'ordre fixé par la Gouvernance (ORDRE). `demandes` (guichet), `attente` (contacts)
    et `fermees` (demandes du guichet closes) sont lues sur GitHub si elles ne sont pas données."""
    debut, fin = periode(maintenant)
    reglages = surete.seuils()
    c = surete.compteur(fin - timedelta(seconds=1), registre.lire("couts"), surete.couts_atelier(), reglages, fin=fin)
    par_chaine, releve, avant = chaines(registre.lire("stats"), debut, fin)
    jour = lambda d: d.astimezone(PARIS).strftime("%d/%m")
    if demandes is None:
        demandes = _lire_github(guichet.ouvertes, "demandes du guichet")
    if attente is None:
        attente = _lire_github(contacts.en_attente, "contacts")
    if fermees is None:
        fermees = [d for d in _lire_github(guichet.toutes, "demandes fermées") or []
                   if d["ferme"] and debut <= quand(d["ferme"].replace("Z", "+00:00")) < fin]
    toutes_questions = questions.etat_questions(registre.lire("questions")).values()
    ouvertes = [q for q in toutes_questions if q["etat"] == "ouverte"]
    decisions = registre.decisions()
    lignes = [f"# Bilan de la semaine du {jour(debut)} au {jour(fin - timedelta(seconds=1))}", ""]

    lignes += [f"## {ORDRE[0]}", ""]
    lignes += [f"- {q['texte']} (Oui : {questions.en_clair(q['si_oui'])}), à trancher par les boutons Telegram"
               for q in ouvertes] or ["- Rien. Tu n'as rien à trancher cette semaine."]
    if guichet.derogation(fin):   # Gouvernance, « Dérogation des premières semaines » : une fois, au bilan prévu
        lignes.append("- Création des comptes : jusqu'ici tu les crées tous. La Direction propose dans son mot (partie 4) "
                      "ce que l'agence pourrait traiter seule. À discuter dans Jarvis, rien ne change sans toi")

    lignes += ["", f"## {ORDRE[1]}", ""]
    if attente is None:
        lignes.append("- Liste illisible ce matin : voir les issues `contact` du dépôt")
    else:
        lignes += [f"- [#{x['numero']}]({x['lien']}) {x['titre']}, préparé le {jour(quand(x['date'].replace('Z', '+00:00')))}"
                   for x in attente] or ["- Aucun message en attente de ta validation"]

    lignes += ["", f"## {ORDRE[2]}", ""]
    if demandes is None:
        lignes.append("- Liste illisible ce matin : voir les issues `guichet` du dépôt")
    else:
        lignes += [f"- {'**Urgent** : ' if x['urgent'] else ''}[#{x['numero']}]({x['lien']}) {x['titre']}"
                   f"{' (PR à fusionner)' if x['pr'] else ''}, depuis le {jour(quand(x['date'].replace('Z', '+00:00')))}"
                   for x in demandes] or ["- Aucune demande ouverte au guichet"]

    lignes += ["", f"## {ORDRE[3]}", ""]
    mot = registre.DOSSIER / "bilans" / f"direction-{fin:%Y-%m-%d}.md"   # écrit le dimanche par la Direction
    if mot.exists():
        lignes += ["### Le mot de la Direction", "", mot.read_text(encoding="utf-8").strip(), ""]
    # Écrit par script : un problème de diffusion figure au bilan même si la Direction n'en a rien dit
    signaux = mesures.signaux_portee(registre.lire("stats"), fin)
    if signaux:
        lignes += ["### Diffusion : à surveiller", ""] + [
            f"- {p['texte'][0].upper() + p['texte'][1:]}."
            + (" Solutions de la Direction : voir son mot plus haut." if p["semaines"] >= mesures.SEMAINES_AVANT_JULES
               else "") for p in signaux] + [""]
    # Écrit par script aussi : un écart du Stratège ouvert depuis 2 semaines figure au bilan, que la Direction en ait
    # parlé ou non (Jules, 15/11 : être prévenu quand les problèmes s'empilent)
    empiles = suivi_ecarts.qui_s_empilent(fin)
    if empiles:
        lignes += ["### Écarts qui s'empilent", "",
                   f"Ce que la mission promet et que l'agence ne fait toujours pas, trouvé par le Stratège. La Direction "
                   f"doit y répondre chaque semaine ; ses solutions, s'il te faut agir, sont dans son mot plus haut.", ""] + [
            f"- {e['constat'].rstrip('.')} (ouvert depuis {e['semaines']} semaines, voie {e['voie']}). "
            f"Remède proposé : {e['remede'].rstrip('.')}." for e in empiles] + [""]

    lignes += ["### Chaînes", "", "| Chaîne | Vidéos sorties | Vues gagnées | Vues au total | Meilleure de la semaine |",
               "|---|---|---|---|---|"]
    for langue in youtube.CHAINES:
        x = par_chaine.get(langue, {"sorties": 0, "gagnees": 0, "total": 0, "meilleure": None})
        m = f"[{x['meilleure'][0]}](https://youtu.be/{x['meilleure'][2]}) (+{x['meilleure'][1]})" if x["meilleure"] else "aucune"
        lignes.append(f"| {NOMS.get(langue, langue)} | {x['sorties']} | +{x['gagnees']} | {x['total']} | {m} |")
    total = sum(x["gagnees"] for x in par_chaine.values())
    lignes += ["", f"Au total : +{total} vues. Dernier relevé : {releve[:16].replace('T', ' ') + ' UTC' if releve else 'aucun'}."
               + ("" if avant else " Aucun relevé avant la période : les vues gagnées comptent tout depuis la sortie."), ""]

    stock = registre.lire("stock")
    dans = lambda l: debut <= quand(l["maj"]) < fin
    prog = sum(1 for l in stock if l["etat"] == "programme" and dans(l))
    rejets = [l["nom"] for l in stock if l["etat"] == "rejete" and dans(l)]
    lignes += ["### Production", "", f"- {prog} vidéos programmées par le flux, sans intervention",
               f"- {len(rejets)} rejetées au contrôle" + (f" : {', '.join(rejets)}" if rejets else "")]
    plus_tard = sorted({l['nom'] for l in stock if l["etat"] == "programme" and quand(l["sortie_prevue"]) and quand(l["sortie_prevue"]) >= fin})
    lignes += [f"- {len(plus_tard)} vidéos programmées au-delà de la période", ""]

    lignes += ["### Organisation", ""]
    lignes += organisation_faite(decisions, debut, fin) or ["- Aucun changement de code, de poste ou de demande cette semaine"]
    # « Le délai se mesure » (MISSION.md) : seuls les besoins qui dépassent leur cible remontent au bilan
    lignes += [f"- Délai dépassé : {r}" for r in delais.phrases_retard(delais.mesure(fin))]
    lignes.append("")

    pauses = registre.lire("pauses")
    actives = [l for l in surete_etat(pauses).values() if l["action"] == "pause"]
    alertes = [l for l in registre.lire("alertes") if debut <= quand(l["date"]) < fin]
    lignes += ["### Sûreté", ""]
    lignes += [f"- En pause : {l['cible']} depuis le {jour(quand(l['date']))} ({l['par']} : {l['raison']})" for l in actives] or ["- Rien en pause"]
    lignes += [f"- Alerte {l['niveau']} le {jour(quand(l['date']))} : {l['message']}" for l in alertes] or ["- Aucune alerte"]

    justes, fausses, indeterminees, verdicts = jugees(decisions, debut, fin)
    lignes += ["", f"## {ORDRE[4]}", ""]
    critique = registre.DOSSIER / "bilans" / f"critique-{fin:%Y-%m-%d}.md"   # écrit le dimanche, la Direction n'y touche pas
    if critique.exists():
        lignes += [critique.read_text(encoding="utf-8").strip(), ""]
    lignes += verdicts or ([] if critique.exists() else ["- Aucune décision jugée cette semaine"])

    lignes += ["", f"## {ORDRE[5]}", ""]
    lignes += _sous_section(argent(debut, fin))
    lignes += _sous_section(investissements())
    part = f", soit {c['pourcent']:.1f} % de ta limite hebdomadaire (objectif : moins de {reglages['claude']['limite_pourcent']} %)" \
        if c["pourcent"] is not None else " (étalon en % de ta limite pas encore mesuré)"
    detail = ", ".join(f"{a} {v['dollars']:.2f} $" for a, v in sorted(c["par_agent"].items()) if v["dollars"])
    lignes += ["### Économie", "", f"- Claude : {c['dollars']:.2f} $ équivalent API{part}" + (f". Détail : {detail}" if detail else ""),
               f"- Modèles gratuits : {c['appels']} appels", "- Dépense réelle : 0 €"]
    if not c["atelier_lu"]:
        lignes.append("- Attention : les séances de l'atelier (chaines-studio) ne sont pas lisibles d'ici, leur coût manque")
    repondues = [q for q in toutes_questions if q["etat"] == "repondue" and debut <= quand(q["date"]) < fin]
    lignes += ["", "### Autonomie", "",
               f"- Tes interventions cette semaine : {len(repondues)} réponse(s) Oui/Non, {len(fermees)} demande(s) du "
               f"guichet traitée(s) (objectif : environ une par semaine)",
               f"- En attente de toi : {len(ouvertes)} question(s), {len(attente or [])} contact(s), "
               f"{len(demandes or [])} demande(s) au guichet",
               "", "### Apprentissage", "",
               f"- Décisions jugées sur les vrais chiffres : {justes} juste(s), {fausses} fausse(s), "
               f"{indeterminees} indéterminée(s)"]
    lignes += ["", "_Chiffres écrits par script, sans modèle. Le mot de la Direction et le critique sont écrits le dimanche soir._"]
    a_faire = [f"{n} {nom}" for n, nom in ((len(ouvertes), "à valider"), (len(attente or []), "contact(s) en attente"),
                                             (len(demandes or []), "demande(s) au guichet")) if n]
    resume = (f"Bilan de la semaine : +{total} vues, {prog} vidéos programmées, {c['dollars']:.2f} $ Claude, "
              f"{', '.join(a_faire) or 'rien à faire'}."
              + (f" {len(empiles)} écart(s) du Stratège s'empile(nt) depuis 2 semaines ou plus : voir la page."
                 if empiles else ""))
    return "\n".join(lignes) + "\n", resume, debut


def nombre(n):
    return "?" if n is None else f"{n:,}".replace(",", " ")


def pourcent(x):
    return f"{x * 100:.1f} %".replace(".", ",")


def argent(debut, fin, seuils=None, occasions=None):
    """Bloc Argent : le seuil de monétisation le plus proche avec ce qui manque (photo du Guetteur), la progression
    de chaque chaîne vers son palier le plus avancé, et les occasions de la période (commentaires et mails)."""
    if seuils is None:
        seuils = json.loads(guetteur.SEUILS.read_text(encoding="utf-8")) if guetteur.SEUILS.exists() else {}
    if occasions is None:
        occasions = registre.lire_jsonl(guetteur.OCCASIONS.stem)
    lignes = ["## Argent", ""]
    p = seuils.get("plus_proche")
    if p:
        manque = (p["cible"] - (p["valeur"] or 0)) if p["valeur"] is not None else None
        lignes.append(f"- Seuil le plus proche : {p['texte']} ({pourcent(p['progression'])}"
                      + (f", il manque {nombre(manque)})" if manque and manque > 0 else ")")
                      + f". Photo du Guetteur du {quand(seuils['date']).astimezone(PARIS):%d/%m %Hh%M}")
        meilleurs = {}
        for l in seuils.get("paliers", []):
            if l["progression"] > meilleurs.get(l["chaine"], {"progression": -1})["progression"]:
                meilleurs[l["chaine"]] = l
        for langue, l in meilleurs.items():
            detail = ", ".join(f"{nombre(c['valeur'])}/{nombre(c['cible'])} {guetteur.NOMS_CRITERES[c['critere']]}"
                               for c in l["criteres"])
            lignes.append(f"  - {NOMS.get(langue, langue)} : {pourcent(l['progression'])} du palier « {l['nom']} » ({detail})")
    else:
        lignes.append("- Seuils : pas encore de photo du Guetteur")
    periode_ = [o for o in occasions if quand(o.get("date")) and debut <= quand(o["date"]) < fin]
    vraies = [o for o in periode_ if o.get("occasion")]
    lignes += [f"- Occasion : {o['type']} ({o.get('source', 'commentaire')}, {NOMS.get(o.get('chaine'), 'aucune chaîne')}) "
               f"{o['lien']}" for o in vraies] or ["- Aucune vraie occasion (collaboration, achat) cette semaine"]
    autres = {}
    for o in periode_:
        if not o.get("occasion"):
            autres[o["type"]] = autres.get(o["type"], 0) + 1
    if autres:
        lignes.append("- Autres commentaires relevés : " + ", ".join(f"{n} {t}" for t, n in sorted(autres.items())))
    lignes += ["- Revenus : 0 € (aucune chaîne monétisée)", ""]
    return lignes


def investissements(cas=None, ecarts=None):
    """Section de l'Analyste : référence « ne rien acheter », proposition par poche (€ de Jules, $ de sa limite Claude,
    jamais additionnées) et montant qui suffit, le cas à éviter, l'écart prévu / réalisé des achats en cours."""
    cas = analyste.derniers_cas() if cas is None else cas
    ecarts = analyste.ecarts()[1] if ecarts is None else ecarts
    lignes = ["## Investissements", ""]
    if not cas:
        return lignes + ["- Pas encore de simulation de l'Analyste", f"- Prévu / réalisé : {ecarts}", ""]
    r = cas["reference"]
    if r:
        lignes.append(f"- Ne rien acheter (référence) : {nombre(round(r['vues_6_mois'][1]))} vues sur 6 mois en médiane "
                      f"(de {nombre(round(r['vues_6_mois'][0]))} à {nombre(round(r['vues_6_mois'][2]))}), "
                      f"revenu {r['revenu_eur_6_mois'][1]:.2f} €".replace(".", ","))
    for p in cas["propositions"]:
        devise = analyste.POCHES[p["poche"]]
        lignes.append(f"- Proposition en {'€ de ta poche' if devise == 'EUR' else '$ de ta limite Claude'} : "
                      f"{' + '.join(p['recommande']) or 'rien'} ({p['pourquoi']}). Montant qui suffit : "
                      f"{p['montant_qui_suffit']} {devise} par mois")
    if not cas["ids"]:
        lignes.append("- Aucune amélioration payante proposée par le Chercheur d'outils cette semaine")
    for a in cas["a_eviter"]:
        lignes.append(f"- À éviter : {' + '.join(a)} (ROI médian sous 1 à 6 mois)")
    lignes += [f"- Prévu / réalisé : {ecarts}", "- Tu décides de chaque achat, dans Jarvis (règle : 0 € tant que l'agence "
               "ne gagne rien)", f"- Tableau complet : https://github.com/{DEPOT}/blob/main/registre/tableau-investissements.csv", ""]
    return lignes


def surete_etat(pauses):
    etat = {}
    for l in pauses:
        etat[l["cible"]] = l
    return etat


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    texte, resume, debut = page(datetime.now(timezone.utc))
    if "--essai" in sys.argv:
        print(texte)
        print(resume)
        return
    with registre.seance("bilan") as info:
        dossier = registre.DOSSIER / "bilans"
        dossier.mkdir(exist_ok=True)
        (dossier / f"{debut:%Y-%m-%d}.md").write_text(texte, encoding="utf-8")
        titre = f"Bilan de la semaine du {debut.astimezone(PARIS):%d/%m}"
        r = subprocess.run(["gh", "issue", "create", "-R", DEPOT, "--title", titre, "--body-file", "-"],
                           input=f"{texte}\n\n@{DEPOT.split('/')[0]}", capture_output=True, text=True, encoding="utf-8")
        if r.returncode:
            raise RuntimeError(f"Issue non créée : {r.stderr.strip()[:300]}")
        lien = r.stdout.strip().splitlines()[-1]
        telegram.envoyer(f"{resume}\n\nLa page : {lien}")
        registre.decider("direction", f"bilan envoyé : {titre}", resume)
        info["resultat"] = f"ok : {lien}"
        print(info["resultat"])


if __name__ == "__main__":
    main()
