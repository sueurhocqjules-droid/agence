# Registre

La mémoire commune de l'agence. Chaque agent y lit et y écrit, en ajout seulement (on ne réécrit pas l'historique). Écriture par `agence/registre.py`.

| Fichier | Une ligne = | Colonnes |
|---|---|---|
| `stock.csv` | une vidéo, de l'idée à la mise en ligne | `nom` (sujet-langue), `chaine`, `sujet`, `etat` (idee, ecrit, en_rendu, rendu, controle, programme, publie, rejete), `sortie_prevue`, `video_id`, `maj`, `note` (artefact, mesures du contrôle, défauts) |
| `stats.csv` | une vidéo à un relevé | `releve`, `chaine`, `video_id`, `titre`, `statut`, `sortie`, `vues`, `likes`, `commentaires` |
| `couts.csv` | un passage d'agent | `debut`, `agent`, `duree_s`, `jetons_claude`, `dollars_equiv` (coût équivalent API, unité commune entre modèles), `appels_gratuits`, `resultat` |
| `pauses.csv` | une mise en pause ou une reprise (la dernière ligne d'une cible fait foi) | `date`, `cible` (agent, script, chef d'une équipe, `chaine:en|es|pt`, ou `tout`), `action` (pause, reprise), `par`, `raison` |
| `questions.csv` | une question à Jules sur Telegram, puis sa réponse (la dernière ligne d'un `id` fait foi) | `date`, `id`, `par`, `texte`, `si_oui`, `si_non` (action fermée : `rien`, `pause:<cible>`, `reprise:<cible>`), `etat` (ouverte, repondue), `reponse`, `message_id` |
| `alertes.csv` | une alerte envoyée par la Sûreté (sa `cle` empêche de la renvoyer) | `date`, `cle`, `niveau` (budget, quota, sanction, panne), `message` |
| `telegram.json` | le dernier clic lu sur Telegram | `decalage` |
| `bilans/<date>.md` | le bilan d'une semaine, copie de l'issue envoyée à Jules | |
| `journal/<agent>.jsonl` | un passage d'un agent ou d'un de ses scripts, écrit par le lanceur | `date`, `quoi`, `resultat` (ok, echec, refuse), `code`, `duree_s`, `sortie` (dernières lignes), `bloquant` (ce qui doit remonter), `secrets_en_trop` |
| `decisions.jsonl` | une décision, le journal d'audit | `date`, `auteur`, `decision`, `pourquoi`, `prediction`, `mesure` (le chiffre qui tranchera), `echeance`, `verdict` (rempli par le critique, jamais par l'auteur) |

Heures en UTC, format ISO 8601.
