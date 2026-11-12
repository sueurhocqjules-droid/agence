"""Expert en modèles : vérifie que chaque modèle gratuit attribué répond encore, et passe en secours ceux qui ne répondent plus.

Lancement : python -m agence.lancer expert-modeles   (ou python -m agents.expert_modeles --essai : montre, n'écrit rien)

L'ordre de qualité de chaque poste reste celui du banc d'essai (agence/postes.py). L'Expert écrit seulement la liste
des modèles en panne (registre/modeles_en_panne.json) : postes.demander les essaie en dernier. Chaque passage repart
de zéro, donc un modèle revenu reprend sa place tout seul. Jamais Claude.
"""
import json
import sys

from agence import modeles, postes, registre

PANNES = postes.PANNES


def verifier():
    """{(fournisseur, modele): erreur ou None} pour chaque modèle attribué, un petit appel chacun."""
    resultats = {}
    for liste in postes.POSTES.values():
        for fournisseur, modele, _ in liste:
            if (fournisseur, modele) in resultats:
                continue
            try:
                texte, *_ = modeles.appeler(fournisseur, modele, "Réponds seulement : OK", 200)
                resultats[(fournisseur, modele)] = None if texte.strip() else "réponse vide"
            except Exception as e:  # noqa: BLE001 : une panne est le résultat attendu de la vérification
                resultats[(fournisseur, modele)] = str(e)[:160]
    return resultats


def postes_sans_modele(en_panne):
    return [p for p, liste in postes.POSTES.items() if all(m in en_panne for _, m, _ in liste)]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    essai = "--essai" in sys.argv
    with registre.seance("expert-modeles") if not essai else _rien() as info:
        resultats = verifier()
        en_panne = {m: err for (_, m), err in resultats.items() if err}
        for m, err in en_panne.items():
            print(f"EN PANNE {m} : {err}")
        orphelins = postes_sans_modele(en_panne)
        if orphelins:
            print(f"ALERTE : aucun modèle ne répond pour {', '.join(orphelins)}")
        if not essai:
            ancien = json.loads(PANNES.read_text(encoding="utf-8")) if PANNES.exists() else {}
            PANNES.write_text(json.dumps(en_panne, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
            if set(ancien) != set(en_panne):
                registre.decider("expert-modeles", f"modèles passés en secours : {sorted(en_panne) or 'aucun'}",
                                 "vérification hebdomadaire : ces modèles n'ont pas répondu à un petit appel")
            info["appels_gratuits"] = len(resultats)
            info["resultat"] = (f"ok : {len(resultats) - len(en_panne)}/{len(resultats)} modèles répondent"
                                + (f", postes sans modèle : {', '.join(orphelins)}" if orphelins else ""))
            print(info["resultat"])


class _rien:
    def __enter__(self):
        return {}

    def __exit__(self, *_):
        return False


if __name__ == "__main__":
    main()
