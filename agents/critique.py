"""Critique : juge chaque décision échue sur les vrais chiffres, annule ce qui n'a rien amélioré, tient la mémoire.

Lancement : python -m agence.lancer critique   (ou python -m agents.critique --essai : montre, n'écrit rien)

1. juger_decisions : chaque décision dont l'échéance est passée et qui n'a pas de verdict, quel que soit son auteur
   (Direction et Responsable de l'organisation compris). Sa mesure est recalculée à l'échéance (agence/mesures.py) :
   juste si la valeur attendue est atteinte, fausse sinon, indéterminée sans mesure chiffrée (signalé à son
   auteur, dans son journal).
2. Annulation, seul, de ce qui n'a rien amélioré :
   - annuler_consigne : un changement de consignes ou de réglage reprend son ancien texte (agence/consignes.py) ;
   - annuler_poste : un changement de poste du Responsable de l'organisation est défait. Suppression : le poste
     reprend tout de suite (fin de la pause) et l'Ingénierie remet sa fiche. Fusion : l'Ingénierie la défait.
     Création : le nouveau poste est mis en pause et l'Ingénierie passe sa fiche au statut « supprime ».
3. juger_essais (registre/essais.jsonl) : au bout de la durée minimale d'un essai, il écrit son résultat chiffré ;
   il signale un essai arrêté avant la fin de sa durée (MISSION.md : « le critique vérifie que la durée a été tenue »).
4. tenir_memoire (organisation/MEMOIRE.md) : il relit les leçons proposées par les agents, ajoute celle de chaque
   annulation et de chaque essai jugé, et signale les leçons dont la date de revue est passée.
5. Sa section du mail du lundi (registre/bilans/critique-<lundi>.md), que la Direction ne retouche pas :
   les verdicts de la semaine par script, et un court commentaire d'un modèle gratuit.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

from agence import consignes, essais, ingenierie, lancer, memoire, mesures, organisation, postes, registre
from agents import surete

POSTE = "critique"


def verdict(decision, valeur):
    """(verdict, commentaire, amélioré) d'une décision à partir de la valeur mesurée à l'échéance."""
    avant, attendu = decision.get("avant"), decision.get("attendu")
    if decision.get("mesure") not in mesures.MESURES or not isinstance(attendu, (int, float)):
        return "indeterminee", "prédiction sans mesure chiffrée", None
    if valeur is None:
        return "indeterminee", "mesure incalculable avec le registre", None
    hausse = avant is None or attendu >= avant
    atteint = valeur >= attendu if hausse else valeur <= attendu
    ameliore = avant is None or (valeur > avant if hausse else valeur < avant)
    chiffres = f"{decision['mesure']} : {avant} avant, {attendu} attendu, {valeur} mesuré"
    if atteint:
        return "juste", chiffres, True
    return "fausse", chiffres + (", dans le bon sens" if ameliore else ", sans amélioration"), ameliore


def echues(decisions, maintenant):
    return [d for d in decisions if d.get("id") and d.get("echeance") and not d["verdict"]
            and mesures.quand(d["echeance"]) <= maintenant]


def annuler_poste(decision, raison, demander=None, pause=None, fiches=None):
    """Défait un changement de poste qui n'a rien amélioré. Renvoie la liste de ce qui a été fait.

    Ce qui est immédiat (reprise ou pause) passe par le registre ; ce qui touche aux fiches est demandé à
    l'Ingénierie, comme le changement lui-même. Rien n'est effacé : Git garde les deux sens.
    """
    o = decision["organisation"]
    demander = demander or ingenierie.demander
    pause = pause or registre.pause
    fiches = organisation.fiches() if fiches is None else fiches
    fait = []
    if o["action"] == "supprimer":
        (p,) = o["postes"]
        pause(p, POSTE, f"suppression annulée par le Critique : {raison}"[:300], action="reprise")
        fait.append(f"{p} repris")
        titre = f"Remettre le poste {p} en service"
        quoi = (f"La suppression du poste `{p}` n'a rien amélioré : le Critique l'annule (le poste a déjà repris). Dans "
                f"`organisation/postes/{p}.md`, remettre `statut` à \"en_service\" si l'Ingénierie l'avait passé à "
                f"\"supprime\", le remettre dans l'équipe de son supérieur (`{o.get('superieur')}`) et dire la date et "
                "la raison de l'annulation sous « Pourquoi ce poste existe ». Si la fiche est déjà en service, ne "
                "changer que cette section")
    elif o["action"] == "fusionner":
        garde, absorbe = o["postes"]
        titre = f"Défaire la fusion de {absorbe} dans {garde}"
        quoi = (f"La fusion du poste `{absorbe}` dans `{garde}` n'a rien amélioré : le Critique l'annule. Remettre "
                f"`{absorbe}` au statut \"en_service\" avec sa mission, ses consignes et ses scripts (propriétaire dans "
                f"`organisation/scripts.toml`), les retirer de la fiche de `{garde}`, et dire la date et la raison de "
                "l'annulation sous « Pourquoi ce poste existe » des deux fiches. Si la fusion n'avait pas été "
                "construite, ne changer que cette section")
    else:
        n = o.get("nouveau")
        if n not in fiches:
            registre.decider(POSTE, f"annulation du changement de poste {decision['id']} (creer)",
                             f"{raison} ; le poste {n} n'a jamais été construit : rien à défaire")
            return [f"{n} jamais construit : rien à défaire"]
        pause(n, POSTE, f"création annulée par le Critique : {raison}"[:300])
        fait.append(f"{n} en pause")
        titre = f"Supprimer le poste {n}"
        quoi = (f"La création du poste `{n}` n'a rien amélioré : le Critique l'annule (le poste est déjà en pause). "
                f"Dans `organisation/postes/{n}.md`, passer `statut` à \"supprime\" et dire la date et la raison sous "
                f"« Pourquoi ce poste existe » ; le retirer de l'équipe de son supérieur. Garder son module et ses "
                "tests : Git garde le retour arrière")
    try:
        numero = demander(titre, quoi, raison, "le Critique",
                          f"décision {decision['id']} jugée fausse au journal d'audit (registre/decisions.jsonl)")
        fait.append(f"demande à l'Ingénierie #{numero}" if numero else "demande à l'Ingénierie non envoyée (essai)")
    except (subprocess.CalledProcessError, OSError, ValueError) as e:
        erreur = str(getattr(e, "stderr", "") or e)[-200:]
        fait.append(f"demande à l'Ingénierie refusée : {erreur}")
        lancer.noter_journal(POSTE, {"date": registre.maintenant(), "quoi": "annuler_poste", "resultat": "echec",
                                     "bloquant": f"« {titre} » n'a pas pu être demandé à l'Ingénierie : {erreur}"})
    registre.decider(POSTE, f"annulation du changement de poste {decision['id']} ({o['action']})",
                     f"{raison} ; {', '.join(fait)}"[:600])
    return fait


def juger_decisions(maintenant, essai, annuler_un_poste=annuler_poste):
    """Juge les décisions échues et annule les changements sans amélioration. Renvoie les verdicts rendus."""
    donnees = mesures.charger(surete.couts_atelier())
    rendus = []
    for d in echues(donnees["decisions"], maintenant):
        echeance = mesures.quand(d["echeance"])
        valeur = mesures.valeur(d["mesure"], echeance, donnees) if d.get("mesure") in mesures.MESURES else None
        v, commentaire, ameliore = verdict(d, valeur)
        rendu = {"id": d["id"], "auteur": d["auteur"], "decision": d["decision"], "verdict": v,
                 "commentaire": commentaire, "date": d["date"], "pourquoi": d.get("pourquoi"), "annule": None}
        rendus.append(rendu)
        print(f"{v.upper()} {d['id']} ({d['decision']}) : {commentaire}")
        if essai:
            continue
        registre.juger(d["id"], v, valeur, commentaire)
        if v == "indeterminee":
            lancer.noter_journal(d["auteur"], {"date": registre.maintenant(), "quoi": "critique",
                                               "resultat": "indeterminee",
                                               "note": f"décision {d['id']} non jugeable : {commentaire}. "
                                                       "Une prédiction nomme une mesure de la liste et une valeur attendue."})
        raison = f"{commentaire} : le changement n'a rien amélioré"
        if d.get("changement") and ameliore is False:
            if consignes.annuler(d, raison):
                rendu["annule"] = "ancien texte remis"
        if d.get("organisation") and ameliore is False:
            rendu["annule"] = ", ".join(annuler_un_poste(d, raison))
        if rendu["annule"]:
            print(f"ANNULÉ {d['id']} : {rendu['annule']}")
    return rendus


def resultat_essai(e, donnees):
    """(phrase, chiffres) du résultat d'un essai au bout de sa durée, tirés du registre."""
    debut, fin = mesures.quand(e["debut"]), mesures.quand(e["fin_prevue"])
    mesure = "vues_semaine" if e["chaine"] == essais.TOUTES else f"vues_semaine:{e['chaine']}"
    avant, apres = mesures.valeur(mesure, debut, donnees), mesures.valeur(mesure, fin, donnees)
    chiffres = {"mesure": mesure, "au_debut": avant, "a_la_fin": apres}
    if apres is None:
        return f"durée de {e['duree_jours']} jours tenue, mais aucun relevé pour chiffrer le résultat", chiffres
    texte = (f"durée de {e['duree_jours']} jours tenue. {mesure} : "
             f"{'inconnu' if avant is None else avant} au début, {apres} à la fin")
    if e["chaine"] != essais.TOUTES:
        p = mesures.portee(donnees["stats"], fin).get(e["chaine"], {})
        if p.get("mediane") is not None:
            chiffres.update(mediane_par_video=p["mediane"], videos=p["videos"])
            texte += f" ; {p['mediane']:g} vues par vidéo en médiane sur {p['videos']} vidéos de la dernière semaine"
    return texte, chiffres


def juger_essais(maintenant, essai, donnees=None):
    """Écrit le résultat des essais arrivés au bout de leur durée et relève ceux arrêtés avant.
    Renvoie (essais jugés, lignes pour la section du mail)."""
    donnees = donnees or mesures.charger(surete.couts_atelier())
    juges, lignes = [], []
    for e in essais.a_juger(maintenant):
        texte, chiffres = resultat_essai(e, donnees)
        print(f"ESSAI {e['id']} ({e['chaine']}, « {e['ligne'][:80]} ») : {texte}")
        if not essai:
            essais.noter_resultat(e["id"], POSTE, texte, chiffres)
        juges.append({**e, "resultat_ecrit": texte})
        lignes.append(f"- **essai jugé** : {e['chaine']}, « {e['ligne'][:120]} ». {texte}")
    for e in essais.etat():
        a = e["arret"]
        if a and not a.get("duree_tenue") and mesures.quand(a["date"]) >= maintenant - timedelta(days=7):
            print(f"DURÉE NON TENUE {e['id']} : arrêté le {a['date'][:10]} par {a['par']}, prévu jusqu'au {e['fin_prevue'][:10]}")
            lignes.append(f"- **durée non tenue** : l'essai sur {e['chaine']} (« {e['ligne'][:120]} ») devait durer "
                          f"jusqu'au {e['fin_prevue'][:10]}, {a['par']} l'a arrêté le {a['date'][:10]} : {a['raison'][:200]}. "
                          "Ses chiffres ne permettent pas de conclure")
    return juges, lignes


def tenir_memoire(maintenant, rendus, essais_juges, essai):
    """Relit les leçons proposées, ajoute celles des annulations et des essais jugés. Renvoie les lignes du mail."""
    lignes = []
    if not essai:
        for p, raison in memoire.integrer():
            print(f"LEÇON de {p['par']} {'refusée (' + raison + ')' if raison else 'retenue'} : {p['fait'][:120]}")
            if raison:
                lancer.noter_journal(p["par"], {"date": registre.maintenant(), "quoi": "critique", "resultat": "refuse",
                                                "note": f"leçon non retenue en mémoire ({raison}) : {p['fait'][:200]}"})
            else:
                lignes.append(f"- **leçon retenue** ({p['par']}) : {p['fait'][:200]}")
        for r in (r for r in rendus if r["annule"]):
            refus = memoire.ajouter(
                f"{r['decision'][:200]} ({r['auteur']}, {r['date'][:10]}) n'a rien amélioré : {r['commentaire']}",
                f"registre/decisions.jsonl, {r['id']}",
                "annulé par le Critique ; ne pas le refaire à l'identique sans fait nouveau", jour=maintenant.date())
            lignes.append(f"- **annulé** : {r['decision'][:160]} ({r['auteur']}). {r['annule']}"
                          + ("" if not refus else f" (leçon non écrite : {refus})"))
        for e in essais_juges:
            memoire.ajouter(f"Essai sur {e['chaine']}, « {e['ligne'][:160]} », depuis le {e['debut'][:10]} : "
                            f"{e['resultat_ecrit']}", f"registre/essais.jsonl, {e['id']}",
                            "toute refonte de cette chaîne cite ce résultat", jour=maintenant.date())
    vieilles = memoire.a_revoir(maintenant)
    if vieilles:
        print(f"MÉMOIRE {len(vieilles)} leçon(s) à revoir : " + " ; ".join(l["fait"][:80] for l in vieilles))
        lignes.append(f"- **mémoire** : {len(vieilles)} leçon(s) ont passé leur date de revue, à confirmer ou à sortir : "
                      + " ; ".join(l["fait"][:100] for l in vieilles[:5]))
    return lignes


def section_du_mail(maintenant, rendus, autres=()):
    """Les verdicts de la semaine, puis un commentaire de trois phrases au plus par le modèle gratuit.
    `autres` : lignes des annulations, des essais et de la mémoire, ajoutées telles quelles."""
    semaine = [d for d in registre.decisions() if d["verdict"]
               and mesures.quand(d["verdict"]["date"]) >= maintenant - timedelta(days=7)]
    suite = ("\n\n" + "\n".join(autres)) if autres else ""
    if not semaine:
        return "Aucune décision échue cette semaine : rien à juger." + suite, 0
    lignes = [f"- **{d['verdict']['verdict']}** : {d['decision']} ({d['auteur']}). {d['verdict']['commentaire']}"
              for d in semaine]
    consigne = ("Tu es le critique interne d'une petite agence de vidéos courtes. Voici les verdicts de la semaine, "
                "calculés sur les vrais chiffres :\n" + "\n".join(lignes) +
                "\n\nÉcris trois phrases au plus, en français, sans tiret long : ce qui a marché, ce qui n'a pas marché, "
                "et si une semaine suffit pour séparer la chance du choix. N'invente aucun chiffre.")
    try:
        texte, *_ = postes.demander("critique", consigne)
        commentaire, appels = texte.strip(), 1
    except RuntimeError as e:
        commentaire, appels = f"(commentaire indisponible : {str(e)[:120]})", 1
    return "\n".join(lignes) + suite + "\n\n" + commentaire, appels


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    maintenant = datetime.now(timezone.utc)
    if "--essai" in sys.argv:
        rendus = juger_decisions(maintenant, essai=True)
        juges, _ = juger_essais(maintenant, essai=True)
        tenir_memoire(maintenant, rendus, juges, essai=True)
        print(f"ESSAI : {len(rendus)} décision(s) échue(s) et {len(juges)} essai(s) à juger, "
              f"{len(memoire.lire())} leçon(s) en mémoire, rien n'est écrit")
        return
    with registre.seance("critique") as info:
        rendus = juger_decisions(maintenant, essai=False)
        juges, lignes = juger_essais(maintenant, essai=False)
        lignes += tenir_memoire(maintenant, rendus, juges, essai=False)
        texte, appels = section_du_mail(maintenant, rendus, lignes)
        lundi = lancer.debut_semaine(maintenant) + timedelta(days=7)
        dossier = registre.DOSSIER / "bilans"
        dossier.mkdir(exist_ok=True)
        (dossier / f"critique-{lundi:%Y-%m-%d}.md").write_text(texte + "\n", encoding="utf-8", newline="\n")
        info["appels_gratuits"] = appels
        annules = sum(1 for r in rendus if r["annule"])
        info["resultat"] = (f"ok : {len(rendus)} décision(s) jugée(s), {annules} annulation(s), {len(juges)} essai(s) "
                            f"jugé(s), {len(memoire.lire())} leçon(s) en mémoire")
        print(info["resultat"])
        print(json.dumps([{k: r[k] for k in ("id", "auteur", "decision", "verdict", "commentaire", "annule")}
                          for r in rendus], ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
