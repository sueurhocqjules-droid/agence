# Banc des agents

Règle 8 de `organisation/MISSION.md` : aucun nouveau poste, aucun changement de consignes, de modèle ou de code d'agent ne part sans passer son banc. Chaque vraie panne devient un cas, rejoué à chaque changement.

    python -m agence.banc_agents                  # tout le banc (appelle les modèles gratuits)
    python -m agence.banc_agents chef-operations  # les cas d'un poste
    python -m agence.banc_agents --sans-modele    # seulement les cas sans modèle (aussi lancés par les tests)

En CI : `.github/workflows/banc.yml`, sur toute PR (et tout push sur `main`) qui touche un agent, sa fiche, la mission ou le banc. Le banc est vert quand **chaque cas rend le verdict attendu**.

## Trois sortes de cas

| Sorte | Ce qui est rejoué | À quoi on la reconnaît |
|---|---|---|
| En direct | Le modèle du poste répond à la consigne d'aujourd'hui sur les données du cas, puis sa réponse passe par le code de l'agent | `adaptateur` et `entree`, sans `reponse_modele` |
| Enregistré | La mauvaise réponse du modèle repasse dans le code d'aujourd'hui. Sans réseau, toujours le même résultat | `reponse_modele` |
| Témoin | Une sortie fautive donnée telle quelle, que le banc doit refuser. Un témoin qui passe veut dire que le banc ne voit plus la panne | `sortie` et `"attendu": "echec"` |

La Direction et le Stratège tournent sur Claude : le banc ne rejoue pas leur séance (coût). Il vérifie ce qu'ils lisent : leur consigne d'aujourd'hui et ce que le script tire du registre (blocages, réseaux sans stats, portée, demandes sans poste).

## Critères

Le code d'abord, le juge ensuite. Si un critère par code échoue, le juge n'est pas appelé.

- `"type": "code"` avec `verif` : `sans` et `avec` (`motifs`, expressions régulières sans casse), `vide`, `egal` (`valeur`), `retours_justifies`. `sur` : chemin à points dans la sortie (`bloquants.0.leve_le`), vide pour toute la sortie
- `"type": "juge"` : une `question` fermée et la réponse `attendu` (`oui` ou `non`). Un juge par critère. Le juge est un modèle gratuit qui n'est pas Claude (poste `juge-banc` de `agence/postes.py`), à température 0, et il évite le modèle qui a écrit ce qu'il juge. Il répond `oui`, `non` ou `inconnu` ; toute autre réponse vaut `inconnu`

Quand le banc est rouge, il écrit sa cause au journal du Chef des opérations (`registre/journal/chef-operations.jsonl`) comme `bloquant` : le bilan, les cas rouges avec leur détail (8 lignes au plus) et le lien du run GitHub. Une panne ne reste pas sans trace.

Verdict d'un cas : `echec` si un critère échoue, sinon `inconnu` si un juge ou le modèle du poste n'a pas pu trancher, sinon `passe`. **`inconnu` n'est pas un passage** : dans le doute le changement ne part pas, on relance le banc.

## Ajouter un cas

Un fichier `<id>.json` ici, avec `id` (le nom du fichier), `poste` (une fiche de `organisation/postes/`), `panne` (la vraie panne, sa date, sa preuve), `criteres`, et soit `adaptateur` + `entree` (+ `reponse_modele`), soit `sortie` + `"attendu": "echec"`. Les adaptateurs (`agence/banc_agents.py`) font passer les données par le vrai code de l'agent ; un nouveau poste au banc demande le sien.

Chaque panne a au moins un cas qui doit passer et un témoin qui doit échouer. Les cas existants sont des fichiers protégés (règle 9) : on en ajoute, on n'en retire pas et on ne les assouplit pas.

## Cas au 13/11/2026

| Panne | Cas |
|---|---|
| Le Chef des opérations invente des retours | `chef-operations-retours-inventes` (enregistré), `chef-operations-semaine-calme-direct`, `temoin-chef-operations-retour-invente` |
| Des pannes réparées comptées comme ouvertes | `chef-operations-panne-levee-direct`, `direction-blocage-leve` |
| La Recherche propose le relais DSH | `chercheur-outils-dsh-refuse` et `chef-recherche-dsh-refuse` (enregistrés), `chercheur-outils-relais-direct`, `temoin-chercheur-outils-relais` |
| La Recherche annonce un gain impossible (texte seulement, « vers 0 ») et un outil qui demande un GPU | `chef-recherche-gain-impossible` (enregistré, reconstitué) |
| La Recherche propose des preuves qui ne correspondent pas au titre, et une pub de marque (15/11) | `chef-recherche-preuves-pas-reprises` (enregistré, reconstitué) |
| La Direction croit que le code repasse par Jules | `direction-code-a-l-ingenierie`, `temoin-direction-code-a-jules` |
| Des réseaux diffusent sans stats, personne ne le voit (15/11) | `stratege-reseaux-sans-stats`, `temoin-stratege-reseaux-sans-stats` |
| La chaîne espagnole n'est pas diffusée, personne ne le voit (13/11) | `stratege-chaine-non-diffusee`, `temoin-stratege-chaine-non-diffusee` |
| Des commentaires et des mails sans poste pour y répondre (14/11) | `stratege-reponses-sans-poste`, `temoin-stratege-reponses-sans-poste` |

Cible de la règle 8 : 20 à 50 cas. Les réponses enregistrées des deux premières pannes sont reconstituées (les originales n'ont pas été gardées) ; les suivantes devront garder la vraie réponse du modèle.
