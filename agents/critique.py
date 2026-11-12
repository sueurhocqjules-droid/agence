"""Critique : juge chaque décision échue sur les vrais chiffres, annule les changements qui n'ont rien amélioré.

Lancement : python -m agence.lancer critique   (ou python -m agents.critique --essai : montre, n'écrit rien)

1. juger_decisions : chaque décision dont l'échéance est passée et qui n'a pas de verdict. Sa mesure est
   recalculée à l'échéance (agence/mesures.py) : juste si la valeur attendue est atteinte, fausse sinon,
   indéterminée sans mesure chiffrée (signalé à son auteur, dans son journal).
2. annuler_consigne : un changement de consignes ou de réglage dont la mesure ne s'est pas améliorée est annulé.
3. Sa section du mail du lundi (registre/bilans/critique-<lundi>.md), que la Direction ne retouche pas :
   les verdicts de la semaine par script, et un court commentaire d'un modèle gratuit.
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from agence import consignes, lancer, mesures, postes, registre
from agents import surete


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


def juger_decisions(maintenant, essai):
    """Juge les décisions échues et annule les changements sans amélioration. Renvoie les verdicts rendus."""
    donnees = mesures.charger(surete.couts_atelier())
    rendus = []
    for d in echues(donnees["decisions"], maintenant):
        echeance = mesures.quand(d["echeance"])
        valeur = mesures.valeur(d["mesure"], echeance, donnees) if d.get("mesure") in mesures.MESURES else None
        v, commentaire, ameliore = verdict(d, valeur)
        rendus.append({"id": d["id"], "auteur": d["auteur"], "decision": d["decision"], "verdict": v,
                       "commentaire": commentaire})
        print(f"{v.upper()} {d['id']} ({d['decision']}) : {commentaire}")
        if essai:
            continue
        registre.juger(d["id"], v, valeur, commentaire)
        if v == "indeterminee":
            lancer.noter_journal(d["auteur"], {"date": registre.maintenant(), "quoi": "critique",
                                               "resultat": "indeterminee",
                                               "note": f"décision {d['id']} non jugeable : {commentaire}. "
                                                       "Une prédiction nomme une mesure de la liste et une valeur attendue."})
        if d.get("changement") and ameliore is False:
            consignes.annuler(d, f"{commentaire} : le changement n'a rien amélioré")
    return rendus


def section_du_mail(maintenant, rendus):
    """Les verdicts de la semaine, puis un commentaire de trois phrases au plus par le modèle gratuit."""
    semaine = [d for d in registre.decisions() if d["verdict"]
               and mesures.quand(d["verdict"]["date"]) >= maintenant - timedelta(days=7)]
    if not semaine:
        return "Aucune décision échue cette semaine : rien à juger.", 0
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
    return "\n".join(lignes) + "\n\n" + commentaire, appels


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    maintenant = datetime.now(timezone.utc)
    if "--essai" in sys.argv:
        print(f"ESSAI : {len(juger_decisions(maintenant, essai=True))} décision(s) échue(s) à juger, rien n'est écrit")
        return
    with registre.seance("critique") as info:
        rendus = juger_decisions(maintenant, essai=False)
        texte, appels = section_du_mail(maintenant, rendus)
        lundi = lancer.debut_semaine(maintenant) + timedelta(days=7)
        dossier = registre.DOSSIER / "bilans"
        dossier.mkdir(exist_ok=True)
        (dossier / f"critique-{lundi:%Y-%m-%d}.md").write_text(texte + "\n", encoding="utf-8", newline="\n")
        info["appels_gratuits"] = appels
        info["resultat"] = f"ok : {len(rendus)} décision(s) jugée(s)"
        print(info["resultat"])
        print(json.dumps(rendus, ensure_ascii=False)[:2000])


if __name__ == "__main__":
    main()
