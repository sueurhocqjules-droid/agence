# Registre

La mémoire commune de l'agence. Chaque agent y lit et y écrit, en ajout seulement (on ne réécrit pas l'historique). Écriture par `agence/registre.py`.

| Fichier | Une ligne = | Colonnes |
|---|---|---|
| `stock.csv` | une vidéo, de l'idée à la mise en ligne | `nom` (sujet-langue), `chaine`, `sujet`, `etat` (idee, ecrit, rendu, controle, programme, publie, rejete), `sortie_prevue`, `video_id`, `maj` |
| `stats.csv` | une vidéo à un relevé | `releve`, `chaine`, `video_id`, `titre`, `statut`, `sortie`, `vues`, `likes`, `commentaires` |
| `couts.csv` | un passage d'agent | `debut`, `agent`, `duree_s`, `jetons_claude`, `dollars_equiv` (coût équivalent API, unité commune entre modèles), `appels_gratuits`, `resultat` |
| `decisions.jsonl` | une décision | `date`, `auteur`, `decision`, `pourquoi`, `prediction`, `mesure` (le chiffre qui tranchera), `echeance`, `verdict` (rempli par le critique, jamais par l'auteur) |

Heures en UTC, format ISO 8601.
