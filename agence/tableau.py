"""Tableau de bord de l'agence : registre/tableau.md, réécrit à chaque réveil.

Lu par Jules et par Claude. Seulement des chiffres tirés du registre, écrits
par les scripts : l'agent ne peut pas les changer (fichier protégé).   python -m agence.tableau
"""
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from agence import lancer, registre

SORTIE = registre.DOSSIER / "tableau.md"


def _date(texte):
    try:
        d = datetime.fromisoformat(str(texte).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _nombre(texte):
    try:
        return float(texte or 0)
    except ValueError:
        return 0.0


def youtube(stats, maintenant):
    """Par chaîne : vues totales au dernier relevé, gagnées en 7 jours, nombre de vidéos publiques."""
    par_releve = defaultdict(lambda: defaultdict(dict))
    for l in stats:
        par_releve[l["chaine"]][l["releve"]][l["video_id"]] = int(_nombre(l["vues"]))
    lignes = []
    for chaine, releves in sorted(par_releve.items()):
        dates = sorted(releves, key=lambda r: _date(r) or datetime.min.replace(tzinfo=timezone.utc))
        dernier = releves[dates[-1]]
        ancien = next((releves[r] for r in reversed(dates) if (_date(r) or maintenant) <= maintenant - timedelta(days=7)),
                      None)
        total = sum(dernier.values())
        gain = total - sum(ancien.values()) if ancien is not None else None
        lignes.append((chaine, total, gain, len(dernier), dates[-1][:16]))
    return lignes


def diffusions(lignes, depuis):
    compte = Counter((l["reseau"], l["etat"]) for l in lignes if (_date(l["date"]) or depuis) > depuis)
    reseaux = sorted({r for r, _ in compte})
    return [(r, compte[(r, "publie")], sum(n for (rr, e), n in compte.items() if rr == r and e != "publie"))
            for r in reseaux]


def couts(lignes, depuis):
    par_agent = defaultdict(float)
    for l in lignes:
        if (_date(l["debut"]) or depuis) >= depuis:
            par_agent[l["agent"]] += _nombre(l["dollars_equiv"])
    return dict(par_agent)


def ecrire(maintenant=None):
    maintenant = maintenant or datetime.now(timezone.utc)
    semaine = lancer.debut_semaine(maintenant)
    sept_jours = maintenant - timedelta(days=7)
    from agents import surete
    reglages = surete.seuils()["claude"]
    part = surete.part_semaine(maintenant, surete.seuils())
    depenses = couts(registre.lire("couts"), semaine)
    total = sum(depenses.values())
    revenus = registre.lire("revenus")

    t = [f"# Tableau de bord ({maintenant.strftime('%d/%m/%Y %H:%M')} UTC)", "",
         "Écrit par les scripts à partir du registre. Ne pas modifier à la main.", "",
         "## Argent", "",
         f"- Revenus encaissés : **{sum(_nombre(r['montant_eur']) for r in revenus):.2f} €** "
         f"({len(revenus)} ligne(s) dans registre/revenus.csv)"]
    t += [f"  - {r['date'][:10]} {r['source']} : {r['montant_eur']} € ({r['preuve']})" for r in revenus[-5:]]
    t += ["", "## Audience YouTube", "", "| chaîne | vues totales | vues gagnées 7 j | vidéos | relevé |", "|---|---|---|---|---|"]
    t += [f"| {c} | {v} | {'?' if g is None else g} | {n} | {r} |" for c, v, g, n, r in youtube(registre.lire("stats"), maintenant)]
    t += ["", "## Diffusions des 7 derniers jours", "", "| réseau | publiées | erreurs |", "|---|---|---|"]
    t += [f"| {r} | {p} | {e} |" for r, p, e in diffusions(registre.lire("diffusions"), sept_jours)]
    t += ["", f"## Consommation de l'agence cette semaine (depuis le {semaine.strftime('%d/%m %H:%M')} UTC)", "",
          f"- Total : **{total:.2f} $** équivalent API (≈ {total / reglages['dollars_par_pourcent']:.1f} % de la limite "
          f"hebdo de Jules)",
          "- Part de l'agence : " + (f"{part:.0f} $ ({reglages['part_pourcent']} %)" if part is not None
                                     else f"lancement, carte blanche jusqu'au {reglages['lancement_jusqu_au']} "
                                          f"(réserve de Jules : {reglages['reserve_pourcent']} %)")]
    t += [f"  - {a} : {d:.2f} $" for a, d in sorted(depenses.items(), key=lambda x: -x[1]) if d]
    SORTIE.write_text("\n".join(t) + "\n", encoding="utf-8")
    return SORTIE


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(ecrire())
