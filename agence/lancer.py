"""Lanceur unique : tout agent ou script de l'agence passe par ici.

    python -m agence.lancer <nom> [arguments transmis au programme]

1. Retrouve sa fiche (organisation/postes/) ou son entrée (organisation/scripts.toml, avec son propriétaire)
2. Refuse s'il est en pause : lui, l'un de ses supérieurs, ou toute l'agence (registre/pauses.csv)
3. Refuse si son budget est atteint : dollars Claude de la semaine, appels gratuits du jour (champ budget de la fiche)
4. Le lance avec ses seuls secrets : toute variable d'allure secrète qu'il n'a pas déclarée est retirée
5. Note le passage au journal du responsable (registre/journal/<agent>.jsonl), et tout refus au journal d'audit
"""
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

from agence import organisation, registre

ALLURE_SECRETE = re.compile(r"TOKEN|KEY|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|COOKIE", re.IGNORECASE)
TOUT = "tout"


def env_cloisonne(environ, autorises):
    """Copie de l'environnement sans les variables d'allure secrète non déclarées."""
    return {k: v for k, v in environ.items() if k in autorises or not ALLURE_SECRETE.search(k)}


def pause_active(cibles, pauses):
    """Renvoie la ligne de pause qui bloque l'une des cibles, sinon None. La dernière ligne d'une cible fait foi."""
    etat = {}
    for ligne in pauses:
        etat[ligne["cible"]] = ligne
    for cible in cibles:
        ligne = etat.get(cible)
        if ligne and ligne["action"] == "pause":
            return ligne
    return None


def debut_semaine(maintenant):
    lundi = maintenant - timedelta(days=maintenant.weekday())
    return lundi.replace(hour=0, minute=0, second=0, microsecond=0)


def budget_atteint(nom, budget, couts, maintenant):
    """Renvoie la raison si le budget est atteint, sinon None. Semaine = depuis lundi 0h UTC, jour = depuis 0h UTC."""
    if not budget:
        return None
    semaine, jour = debut_semaine(maintenant), maintenant.replace(hour=0, minute=0, second=0, microsecond=0)
    dollars = appels = 0.0
    for ligne in couts:
        if ligne["agent"] != nom:
            continue
        quand = datetime.fromisoformat(ligne["debut"])
        if quand >= semaine:
            dollars += float(ligne["dollars_equiv"] or 0)
        if quand >= jour:
            appels += float(ligne["appels_gratuits"] or 0)
    plafond_dollars = budget.get("claude_usd_semaine", 0)
    plafond_appels = budget.get("appels_gratuits_jour", 0)
    if plafond_dollars and dollars >= plafond_dollars:
        return f"budget Claude de la semaine atteint : {dollars:.2f} $ sur {plafond_dollars} $"
    if plafond_appels and appels >= plafond_appels:
        return f"appels gratuits du jour atteints : {appels:.0f} sur {plafond_appels}"
    return None


def preparer(nom, postes, liste_scripts):
    """Renvoie (responsable, module, secrets autorisés, budget) pour un agent ou un script."""
    if nom in liste_scripts:
        s = liste_scripts[nom]
        if s["proprietaire"] not in postes:
            raise ValueError(f"Script {nom} : propriétaire inconnu {s['proprietaire']!r}")
        return s["proprietaire"], s["module"], set(s.get("secrets", [])), s.get("budget")
    if nom in postes:
        f = postes[nom]
        if "module" not in f:
            raise ValueError(f"L'agent {nom} n'est pas encore construit (pas de champ module dans sa fiche)")
        return nom, f["module"], set(f.get("env", [])), f.get("budget")
    raise ValueError(f"Ni agent ni script : {nom!r}")


def noter_journal(responsable, entree):
    dossier = registre.DOSSIER / "journal"
    dossier.mkdir(exist_ok=True)
    with open(dossier / f"{responsable}.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(entree, ensure_ascii=False) + "\n")


def lancer(nom, arguments):
    postes, liste_scripts = organisation.fiches(), organisation.scripts()
    responsable, module, autorises, budget = preparer(nom, postes, liste_scripts)
    cibles = [nom] + organisation.chaine_de_commandement(responsable, postes) + [TOUT]
    if liste_scripts.get(nom, {}).get("hors_pause"):
        cibles = [nom]  # sûreté et réponses de Jules : une pause générale ne doit pas couper le moyen de la lever
    maintenant = datetime.now(timezone.utc)

    refus = None
    pause = pause_active(cibles, registre.lire("pauses"))
    if pause:
        refus = f"en pause ({pause['cible']}, par {pause['par']} : {pause['raison']})"
    else:
        refus = budget_atteint(nom, budget, registre.lire("couts"), maintenant)
    if refus:
        print(f"REFUS {nom} : {refus}")
        registre.decider("lanceur", f"ne pas lancer {nom}", refus)
        noter_journal(responsable, {"date": registre.maintenant(), "quoi": nom, "resultat": "refuse",
                                    "bloquant": refus})
        return 0  # un refus prévu n'est pas une panne

    # Le vrai cloisonnement est fait par le workflow (une étape par agent, avec ses seuls secrets) :
    # un secret non déclaré présent ici trahit une étape mal réglée, on le signale.
    en_trop = sorted(k for k in os.environ if ALLURE_SECRETE.search(k) and k not in autorises)
    if en_trop:
        print(f"ALERTE {nom} : secrets non déclarés dans l'environnement, retirés pour le programme : {' '.join(en_trop)}")

    debut, sortie = time.time(), []
    with subprocess.Popen([sys.executable, "-m", module, *arguments], env=env_cloisonne(os.environ, autorises),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
                          errors="replace") as proc:
        for ligne in proc.stdout:
            print(ligne, end="", flush=True)
            sortie.append(ligne.rstrip())
    entree = {"date": registre.maintenant(), "quoi": nom, "resultat": "ok" if proc.returncode == 0 else "echec",
              "code": proc.returncode, "duree_s": round(time.time() - debut), "sortie": "\n".join(sortie[-8:])[-800:]}
    if en_trop:
        entree["secrets_en_trop"] = en_trop
    if proc.returncode:
        entree["bloquant"] = f"{nom} a échoué (code {proc.returncode}), voir la sortie"
    noter_journal(responsable, entree)
    return proc.returncode


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(lancer(sys.argv[1], sys.argv[2:]))


if __name__ == "__main__":
    main()
