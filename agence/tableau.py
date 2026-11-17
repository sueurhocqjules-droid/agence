"""Tableau de bord de l'agence : registre/tableau.md, réécrit à chaque réveil et après chaque séance du Pilote.

Lu par le Pilote (où en est-on), par le juge (les faits) et par Jules. Seulement des chiffres tirés du registre, écrits
par les scripts : l'agent ne peut pas les changer (fichier protégé).   python -m agence.tableau
"""
import json
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
    seances = [s for s in registre.lire_jsonl("journal/pilote")
               if s.get("quoi") == "pilote" and (_date(s.get("date")) or sept_jours) > sept_jours] \
        if (registre.DOSSIER / "journal" / "pilote.jsonl").exists() else []
    juge = []
    historique = registre.DOSSIER / "juge" / "historique.jsonl"
    if historique.exists():
        juge = [json.loads(l) for l in historique.read_text(encoding="utf-8").splitlines() if l.strip()][-5:]

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
    t += ["", "## Séances du Pilote (7 jours)", "",
          f"- {len(seances)} séance(s), {sum(1 for s in seances if s.get('resultat') == 'ok')} sans erreur, "
          f"{sum(1 for s in seances if s.get('arret'))} arrêtée(s) par l'anti-emballement",
          f"- Code gardé : {sum(int(s.get('gardes') or 0) for s in seances)} fichier(s), retiré par le tri : "
          f"{sum(int(s.get('retires') or 0) for s in seances)}"]
    t += [f"  - {s.get('date', '')[:16]} : {s.get('resultat')}, {s.get('cout_usd')} $, juge {s.get('juge')}/10"
          + (f", arrêt : {s['arret']}" if s.get("arret") else "") for s in seances[-5:]]
    if juge:
        t += ["", "## Derniers avis du juge", ""]
        t += [f"- {j.get('date', '')[:16]} ({j.get('modele')}) {j.get('note')}/10, code {j.get('code')} : "
              f"{j.get('resume')}" for j in juge]
    SORTIE.write_text("\n".join(t) + "\n", encoding="utf-8")
    return SORTIE


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(ecrire())
