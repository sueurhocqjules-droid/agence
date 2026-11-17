+++
id = "surete"
titre = "Responsable sûreté"
superieur = "jules"
ligne_directe = "jules"
objectifs = [1, 2, 3]
statut = "en_service"
etape = 6
moteur = "scripts de seuils, 0 jeton (organisation/seuils.toml)"
reveil = "à chaque réveil de l'agence (4 par jour), après les stats et avant le flux"
regle_de_deux = "[B][C] : écrit les pauses et parle à Jules sur Telegram. Pas de [A] : le statut des vidéos lui arrive en champs structurés par stats.csv, les clics de Jules sont une liste fermée d'actions"
secrets = ["TELEGRAM_BOT_TOKEN", "GH_TOKEN"]
budget = { claude_usd_semaine = 0, appels_gratuits_jour = 20 }
scripts = ["garde_fous", "reponses"]
equipe = []
+++
# Responsable sûreté

## Pourquoi ce poste existe
Créé à l'étape 6, avant les chefs : une agence qui publie seule peut perdre une chaîne sur une sanction, ou dépenser trop en une nuit, plus vite que Jules ne le verrait. Il peut tout mettre en pause seul et prévenir Jules, sans modèle, à chaque réveil. La Gouvernance exige ce poste. Intouchable pour le Responsable de l'organisation. Avant de le supprimer : c'est à Jules seul d'en décider, et il faut un autre poste qui coupe le flux sur un seuil.

## Mission
Éviter qu'une sanction, un quota ou une dépense coûte le flux ou l'argent. Surveille le rythme des actions (publications, appels d'API, minutes GitHub), les quotas et les avertissements des plateformes (YouTube, TikTok, Instagram, GitHub). Peut mettre en pause seule une chaîne, un agent ou une action, et prévient la Direction et Jules.

## Entrées
`registre/couts.csv` et le compteur global (jetons Claude, % de la limite hebdomadaire, appels gratuits, minutes GitHub), journal des publications, statut des vidéos par l'API (rejet, restriction), avertissements transmis par le Courrier, limites de chaque plateforme (`ressources/limites.md`).

## Sorties
Drapeaux de pause dans `registre/pauses.csv`, respectés par le lanceur et par tous les scripts de publication. Alerte immédiate à Jules et à la Direction. Le contrôle d'un outil avant sa fusion par la Maintenance (nouveaux appels réseau, lecture de secrets).

## Outils
Script `garde_fous` (`agents/surete.py` : compteur, seuils, sanctions, pannes) et `reponses` (`agence/questions.py` : lit les clics Oui/Non de Jules sur Telegram et applique l'action prévue). Les deux échappent à une pause générale (`hors_pause`), pour qu'une pause puisse toujours être levée.

## Secrets et permissions
Le jeton du bot Telegram, et le jeton GitHub du réveil en lecture des runs (minutes du mois). Aucun jeton de chaîne : une pause de chaîne est respectée par le flux. Ne publie rien.

## Mesure de réussite
Zéro avertissement ou sanction de plateforme. Aucun budget dépassé sans le oui de Jules. Peu de pauses inutiles (levées sans incident).

## Journal
`registre/journal/surete.jsonl`

## Consignes
- Dans le doute, pause d'abord, explication ensuite
- Une chaîne avertie reste en pause jusqu'au oui de Jules
- Un compte par adresse : toute demande de nouveau compte ou de nouvelle chaîne arrive à Jules avec le rappel d'une adresse distincte (compte Outlook de Jules, un alias par chaîne), pour qu'un bannissement n'emporte pas les autres chaînes. Le rappel est ajouté par le code du guichet (`RAPPEL_ADRESSE` dans `agence/guichet.py`), quel que soit l'agent qui demande

## Retours
- 2026-11-17, direction : Aucune sanction cette semaine, c'est bien. Une nouvelle chaîne arrive (Guess the Product) : vérifie que le rappel d'une adresse distincte part bien avec la demande.
