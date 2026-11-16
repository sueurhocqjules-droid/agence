"""Concepts du Veilleur au stade « propose » : ce que la Direction lit, et le stade qu'elle leur donne.

Propriétaire : la Direction (`agents/direction.py`). Le registre ne se réécrit pas : une réponse ajoute une ligne à
`registre/concepts.jsonl` pour le même lien, avec le nouvel état. La ligne la plus récente d'un lien fait foi.
"""
import hashlib
import json

from agence import registre

REPONSES = ["lancer_chaine_existante", "nouvelle_chaine", "ecarte"]
POTENTIELS = ["viral", "affiliation", "autre"]
ETATS = {"lancer_chaine_existante": "chaine_existante", "nouvelle_chaine": "nouvelle_chaine", "ecarte": "ecarte"}


def identifiant(lien):
    return "c" + hashlib.sha1(lien.encode("utf-8")).hexdigest()[:8]


def derniers():
    """La ligne la plus récente de chaque concept, par lien."""
    par_lien = {}
    for l in registre.lire_jsonl("concepts"):
        par_lien[l["lien"]] = l
    return par_lien


def ouverts():
    """Les concepts encore au stade « propose », en champs fermés."""
    return [{"id": identifiant(c["lien"]), "titre": str(c.get("titre"))[:200], "source": c["lien"],
             **{k: c.get(k) for k in ("vues", "ratio", "effort", "cout_estime_usd", "destination")}}
            for c in derniers().values() if c.get("etat") == "propose"]


def appliquer(reponses, auteur="direction"):
    """Fait passer chaque concept répondu à son nouveau stade et note la décision. Renvoie (faits, refus).
    Une réponse avec une `limite` (arrêtée faute de moyens) est notée au journal : le concept garde son stade."""
    par_id = {identifiant(l): c for l, c in derniers().items() if c.get("etat") == "propose"}
    faits, refus, vus = [], [], set()
    for r in reponses or []:
        ident, reponse = r.get("id"), r.get("reponse")
        raison = str(r.get("raison") or "").strip()
        limite = str(r.get("limite") or "").strip()
        if ident not in par_id:
            refus.append(f"concept {ident} : pas au stade propose")
        elif ident in vus:
            refus.append(f"concept {ident} : déjà répondu dans cette séance")
        elif reponse not in REPONSES or r.get("potentiel") not in POTENTIELS or not raison:
            refus.append(f"concept {ident} : réponse, potentiel ou raison hors liste")
        else:
            vus.add(ident)
            c = par_id[ident]
            debut = f"concept {ident} ({str(c.get('titre'))[:60]}) : {reponse}"
            if limite:
                texte = f"{debut} voulu, arrêté faute de moyens : {limite[:200]}"
            else:
                texte = debut
                with open(registre.DOSSIER / "concepts.jsonl", "a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps({**c, "date": registre.maintenant(), "par": auteur, "etat": ETATS[reponse],
                                        "potentiel": r["potentiel"], "raison": raison[:600]}, ensure_ascii=False) + "\n")
            registre.decider(auteur, f"{texte}, potentiel {r['potentiel']}", raison[:600])
            faits.append(texte)
    return faits, refus
