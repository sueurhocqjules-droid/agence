"""Registre des essais (MISSION.md, boucle d'amélioration, point 7 : cohérence et mémoire).

Un essai = une chaîne qui suit une ligne (éditoriale, format) pendant une durée minimale, choisie par l'agence
avec sa raison, pour donner des chiffres exploitables. registre/essais.jsonl, en ajout seulement :
- {"type": "essai", ...}     ouvert par la Direction (`ouvrir`)
- {"type": "resultat", ...}  écrit par le Critique au bout de la durée (`noter_resultat`)
- {"type": "arret", ...}     essai arrêté (`arreter`) : avant la fin de sa durée, le Critique le signale

Règles tenues par code :
- une chaîne garde sa ligne jusqu'au bout de la durée : `ouvrir` refuse un nouvel essai sur une chaîne dont
  l'essai en cours n'a pas fini sa durée, ou n'a pas encore son résultat ;
- toute refonte cite l'essai précédent : le nouvel essai porte `precedent` (identifiant, ligne, résultat),
  recopié par le script, jamais écrit par un modèle.

Voir l'état : python -m agence.essais
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from agence import mesures, registre, youtube

FICHIER = "essais"
TOUTES = "toutes"                 # un essai qui porte sur toutes les chaînes à la fois (un format, par exemple)
DUREE_MIN, DUREE_MAX = 7, 180     # jours : moins d'une semaine ne donne pas de chiffres, plus de six mois n'est plus un essai


def chaines():
    return [*youtube.CHAINES, TOUTES]


def _ecrire(ligne):
    with open(registre.DOSSIER / f"{FICHIER}.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ligne, ensure_ascii=False) + "\n")


def etat(lignes=None):
    """Tous les essais, du plus ancien au plus récent, chacun avec `fin_prevue`, `resultat` et `arret` s'il y en a."""
    lignes = registre.lire_jsonl(FICHIER) if lignes is None else lignes
    essais = {}
    for l in lignes:
        if l.get("type") == "essai":
            fin = mesures.quand(l["debut"]) + timedelta(days=l["duree_jours"])
            essais[l["id"]] = {**l, "fin_prevue": fin.isoformat(timespec="seconds"), "resultat": None, "arret": None}
        elif l.get("id") in essais and l.get("type") in ("resultat", "arret"):
            essais[l["id"]][l["type"]] = {k: v for k, v in l.items() if k not in ("type", "id")}
    return list(essais.values())


def en_cours(chaine, lignes=None):
    """Le dernier essai de la chaîne s'il n'est ni arrêté ni remplacé, ou None."""
    siens = [e for e in etat(lignes) if e["chaine"] == chaine]
    return siens[-1] if siens and not siens[-1]["arret"] else None


def duree_tenue(essai, maintenant):
    return maintenant >= mesures.quand(essai["fin_prevue"])


def ouvrir(par, chaine, ligne, duree_jours, raison, maintenant=None):
    """Note un essai et renvoie son identifiant. ValueError si la chaîne doit encore tenir sa ligne."""
    maintenant = maintenant or datetime.now(timezone.utc)
    ligne, raison = " ".join(str(ligne or "").split())[:300], " ".join(str(raison or "").split())[:400]
    if chaine not in chaines():
        raise ValueError(f"chaîne hors liste : {chaine!r} ({', '.join(chaines())})")
    if not ligne or not raison:
        raise ValueError("un essai dit la ligne suivie et la raison de sa durée")
    if not isinstance(duree_jours, int) or not DUREE_MIN <= duree_jours <= DUREE_MAX:
        raise ValueError(f"durée minimale hors de {DUREE_MIN} à {DUREE_MAX} jours : {duree_jours!r}")
    precedent = next((e for e in reversed(etat()) if e["chaine"] == chaine), None)
    if precedent and precedent["arret"]:      # arrêté : la chaîne est libre, mais le nouvel essai le cite quand même
        cite = (precedent["resultat"] or {}).get("resultat") or f"arrêté : {precedent['arret']['raison']}"
    elif precedent:
        if not duree_tenue(precedent, maintenant):
            raise ValueError(f"la chaîne {chaine} garde sa ligne (« {precedent['ligne'][:80]} ») jusqu'au "
                             f"{precedent['fin_prevue'][:10]} : durée minimale de l'essai {precedent['id']}")
        if not precedent["resultat"]:
            raise ValueError(f"l'essai {precedent['id']} n'a pas encore son résultat (le Critique l'écrit à son "
                             "passage) : une refonte cite le résultat de l'essai précédent")
        if precedent["ligne"] == ligne:
            raise ValueError("même ligne que l'essai en cours : rien ne change")
        cite = precedent["resultat"]["resultat"]
    ident = f"essai-{chaine}-{maintenant:%Y%m%d%H%M%S}"
    _ecrire({"type": "essai", "id": ident, "date": registre.maintenant(), "par": par, "chaine": chaine,
             "ligne": ligne, "debut": maintenant.isoformat(timespec="seconds"), "duree_jours": duree_jours,
             "raison": raison,
             "precedent": precedent and {"id": precedent["id"], "ligne": precedent["ligne"], "resultat": cite}})
    return ident


def noter_resultat(ident, par, resultat, chiffres=None):
    """Le résultat d'un essai au bout de sa durée, écrit par le Critique à partir des chiffres."""
    _ecrire({"type": "resultat", "id": ident, "date": registre.maintenant(), "par": par,
             "resultat": str(resultat)[:400], "chiffres": chiffres or {}})


def arreter(ident, par, raison, maintenant=None):
    """Arrête un essai. Avant la fin de sa durée, la durée n'est pas tenue : le Critique le signale."""
    maintenant = maintenant or datetime.now(timezone.utc)
    essai = next((e for e in etat() if e["id"] == ident), None)
    if not essai or essai["arret"]:
        raise ValueError(f"essai inconnu ou déjà arrêté : {ident!r}")
    if not str(raison or "").strip():
        raise ValueError("un arrêt dit sa raison")
    _ecrire({"type": "arret", "id": ident, "date": maintenant.isoformat(timespec="seconds"), "par": par,
             "raison": str(raison)[:400], "duree_tenue": duree_tenue(essai, maintenant)})


def a_juger(maintenant, lignes=None):
    """Les essais dont la durée est passée et qui n'ont pas encore de résultat."""
    return [e for e in etat(lignes) if not e["resultat"] and not e["arret"] and duree_tenue(e, maintenant)]


def dossier(maintenant=None):
    """Ce que lit la Direction : l'essai de chaque chaîne, ce qu'il reste à tenir, et les chaînes sans essai."""
    maintenant = maintenant or datetime.now(timezone.utc)
    tous = etat()
    courants = {c: en_cours(c) for c in chaines()}
    return {
        "en_cours": [{"id": e["id"], "chaine": e["chaine"], "ligne": e["ligne"], "debut": e["debut"][:10],
                      "duree_jours": e["duree_jours"], "raison": e["raison"], "fin_prevue": e["fin_prevue"][:10],
                      "jours_restants": max(0, (mesures.quand(e["fin_prevue"]) - maintenant).days),
                      "resultat": e["resultat"] and e["resultat"]["resultat"],
                      "refonte_possible": bool(duree_tenue(e, maintenant) and e["resultat"])}
                     for e in courants.values() if e],
        "chaines_sans_essai": [c for c in youtube.CHAINES if not courants[c]],
        "passes": [{"id": e["id"], "chaine": e["chaine"], "ligne": e["ligne"], "duree_jours": e["duree_jours"],
                    "resultat": e["resultat"] and e["resultat"]["resultat"],
                    "arret": e["arret"] and {k: e["arret"].get(k) for k in ("date", "raison", "duree_tenue")}}
                   for e in tous if e not in courants.values()][-6:],
        "regle": "une chaîne garde sa ligne jusqu'à fin_prevue ; une refonte n'est possible que si refonte_possible "
                 "est vrai, et elle cite le résultat de l'essai précédent (recopié par le script)",
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(dossier(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
