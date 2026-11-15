"""Les écarts du Stratège (registre/ecarts.jsonl) : leur état, et ceux qui s'empilent.

Le Stratège rend chaque dimanche tous les écarts qu'il prouve (agents/stratege.py), et suit les anciens : comblé,
ouvert ou abandonné, son dernier suivi fait foi. Un écart encore ouvert depuis SEMAINES_AVANT_JULES semaines
s'empile : la Direction le trouve dans son dossier et doit agir ou dire pourquoi elle l'écarte, et le bilan du lundi
le montre à Jules (même règle qu'une chaîne mal diffusée). Un écart ouvert ne sort jamais de la vue, quel que soit
son âge ; un écart fermé reste visible SUIVI jours.
"""
from datetime import timedelta

from agence import mesures, registre

FICHIER = "ecarts"
SUIVI = timedelta(days=56)
ETATS = ("ouvert", "comble", "abandonne")
JEU = timedelta(days=1)   # d'un dimanche à l'autre, l'heure du réveil varie : 13 jours et demi font 2 semaines


def passes(maintenant):
    """Les écarts du Stratège avec leur dernier état et leur âge en semaines : tous les ouverts, et les fermés depuis
    moins de SUIVI."""
    lignes = registre.lire_jsonl(FICHIER)
    suivis = {s["id"]: s for l in lignes for s in l.get("suivi") or [] if isinstance(s, dict) and s.get("id")}
    res = []
    for l in lignes:
        quand = mesures.quand(l["date"])
        for e in l.get("ecarts") or []:
            s = suivis.get(e.get("id"), {})
            etat = s.get("etat", "ouvert")
            if etat == "ouvert" or maintenant - quand < SUIVI:
                res.append(e | {"date": l["date"][:10], "etat": etat, "suivi": s.get("pourquoi"),
                                "semaines": (maintenant - quand + JEU).days // 7})
    return res


def ouverts(maintenant):
    return [e for e in passes(maintenant) if e["etat"] == "ouvert"]


def qui_s_empilent(maintenant):
    """Les écarts ouverts depuis SEMAINES_AVANT_JULES semaines ou plus, le plus ancien d'abord."""
    return sorted((e for e in ouverts(maintenant) if e["semaines"] >= mesures.SEMAINES_AVANT_JULES),
                  key=lambda e: -e["semaines"])
