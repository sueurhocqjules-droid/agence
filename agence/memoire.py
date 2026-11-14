"""Mémoire de l'entreprise (MISSION.md, règle 7) : organisation/MEMOIRE.md, les leçons apprises, une par ligne.

Chaque leçon : le fait, sa preuve (lien vers le registre, un commit, un run, une issue), la date, ce qu'il change,
la date où le revoir. N'importe quel agent en propose (`proposer`, registre/lecons.jsonl) ; le Critique la tient
(`integrer`, `ajouter`, `retirer`) : lui seul écrit le fichier. La Direction, le Responsable de l'organisation, le
Chef de contenu et le Responsable du revenu la lisent dans leurs données (`dossier`, `pour_un_agent`) avant de décider.
Elle reste courte : `MAXIMUM` leçons, et une leçon dont la date de revue est passée est signalée par le Critique.

Voir l'état : python -m agence.memoire
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone

from agence import organisation, registre

FICHIER = "MEMOIRE.md"
PROPOSITIONS = "lecons"
MAXIMUM = 40
REVOIR_J = 90        # sans date donnée, une leçon se revoit au bout de trois mois
COLONNES = ("fait", "preuve", "date", "change", "revoir")
ENTETE = """# Mémoire de l'entreprise

> Les leçons apprises, une par ligne (MISSION.md, règle 7). Tenue par le Critique (`agents/critique.py`, par
> `agence/memoire.py`) : n'importe quel agent propose une leçon, lui seul écrit ici. Lue avant toute décision
> engageante par la Direction, le Responsable de l'organisation, l'Ingénierie, le Chef de contenu et le
> Responsable du revenu. Elle reste courte : une leçon qui ne change plus aucune décision en sort.

| Fait | Preuve | Date | Ce que ça change | À revoir le |
|---|---|---|---|---|
"""
# Une preuve se vérifie : un fichier du dépôt, un commit, un run, une issue, un lien, ou une décision du journal
PREUVE = re.compile(r"registre/|organisation/|agence/|agents/|\b[0-9a-f]{7,40}\b|\brun \d{6,}|#\d+|https?://|-\d{20}\b")


def chemin():
    return organisation.DOSSIER / FICHIER


def _cellule(texte, n):
    return " ".join(str(texte or "").replace("|", "/").split())[:n]


def _cle(fait):
    return re.sub(r"\W+", " ", str(fait).lower()).strip()


def lire():
    """Les leçons du fichier, dans l'ordre : dicts fait, preuve, date, change, revoir."""
    if not chemin().exists():
        return []
    lecons = []
    for ligne in chemin().read_text(encoding="utf-8").splitlines():
        cellules = [c.strip() for c in ligne.strip().strip("|").split("|")]
        if ligne.startswith("|") and len(cellules) == len(COLONNES) and not set(cellules[0]) <= set("-: ") \
                and cellules[0] != "Fait":
            lecons.append(dict(zip(COLONNES, cellules)))
    return lecons


def ecrire(lecons):
    texte = ENTETE + "".join("| " + " | ".join(l[c] for c in COLONNES) + " |\n" for l in lecons)
    chemin().write_text(texte, encoding="utf-8", newline="\n")


def refus(fait, preuve, change, lecons):
    """Pourquoi cette leçon n'entre pas, ou None."""
    if not _cellule(fait, 400) or not _cellule(change, 300):
        return "il manque le fait ou ce qu'il change"
    if not PREUVE.search(str(preuve or "")):
        return "preuve absente ou invérifiable (fichier du registre, commit, run, issue ou lien attendu)"
    if _cle(fait) in {_cle(l["fait"]) for l in lecons}:
        return "leçon déjà en mémoire"
    if len(lecons) >= MAXIMUM:
        return f"mémoire pleine ({MAXIMUM} leçons) : en retirer une qui ne change plus aucune décision"
    return None


def ajouter(fait, preuve, change, revoir=None, jour=None):
    """Le Critique ajoute une leçon. Renvoie la raison du refus, ou None si elle est écrite."""
    lecons = lire()
    raison = refus(fait, preuve, change, lecons)
    if raison:
        return raison
    jour = jour or datetime.now(timezone.utc).date()
    try:
        revoir = datetime.fromisoformat(str(revoir)[:10]).date() if revoir else None
    except ValueError:
        revoir = None
    lecons.append({"fait": _cellule(fait, 400), "preuve": _cellule(preuve, 200), "date": jour.isoformat(),
                   "change": _cellule(change, 300), "revoir": (revoir or jour + timedelta(days=REVOIR_J)).isoformat()})
    ecrire(lecons)
    return None


def retirer(fait, par, raison):
    """Le Critique sort une leçon qui ne change plus aucune décision. Git garde l'ancienne version."""
    lecons = lire()
    gardees = [l for l in lecons if _cle(l["fait"]) != _cle(fait)]
    if len(gardees) == len(lecons):
        return False
    ecrire(gardees)
    registre.decider(par, f"leçon retirée de la mémoire : {str(fait)[:120]}", raison)
    return True


def proposer(par, fait, preuve, change, revoir=None):
    """Un agent propose une leçon : le Critique la relit à son passage (registre/lecons.jsonl)."""
    with open(registre.DOSSIER / f"{PROPOSITIONS}.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"date": registre.maintenant(), "par": par, "fait": _cellule(fait, 400),
                            "preuve": _cellule(preuve, 200), "change": _cellule(change, 300),
                            "revoir": str(revoir or "")[:10]}, ensure_ascii=False) + "\n")


def integrer():
    """Le Critique traite les propositions en attente. Renvoie [(proposition, raison du refus ou None)]."""
    lignes = registre.lire_jsonl(PROPOSITIONS)
    traitees = {(l["de"], l["proposee_le"], l["fait"]) for l in lignes if l.get("type") == "suite"}
    suites = []
    for p in lignes:
        if p.get("type") == "suite" or (p["par"], p["date"], p["fait"]) in traitees:
            continue
        raison = ajouter(p["fait"], p["preuve"], p["change"], p.get("revoir"))
        with open(registre.DOSSIER / f"{PROPOSITIONS}.jsonl", "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"type": "suite", "date": registre.maintenant(), "de": p["par"], "proposee_le": p["date"],
                                "fait": p["fait"], "suite": "refusee" if raison else "retenue", "raison": raison or ""},
                               ensure_ascii=False) + "\n")
        suites.append((p, raison))
    return suites


def a_revoir(maintenant=None):
    """Les leçons dont la date de revue est passée."""
    jour = (maintenant or datetime.now(timezone.utc)).date().isoformat()
    return [l for l in lire() if l["revoir"] and l["revoir"] <= jour]


def pour_un_agent():
    """Les leçons en court, pour les données d'un agent : le fait et ce qu'il change."""
    return [f"{l['fait']} → {l['change']}" for l in lire()]


def dossier(maintenant=None):
    """Ce que lit la Direction : toutes les leçons, et celles qui sont à revoir."""
    return {"lecons": lire(), "a_revoir": [l["fait"] for l in a_revoir(maintenant)],
            "regle": "relis ces leçons avant toute décision engageante : ne refais pas ce qui a déjà échoué sans fait "
                     "nouveau. Une leçon se propose dans lecons, avec sa preuve ; le Critique la relit"}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(dossier(), ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
