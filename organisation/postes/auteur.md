+++
id = "auteur"
titre = "Auteur des sujets (atelier)"
superieur = "chef-contenu"
objectifs = [1, 4]
statut = "en_service"
etape = 4
moteur = "Claude Opus sur GitHub (chaines-studio, atelier.yml), une séance par semaine. Remplaçant gratuit cherché par la Recherche"
reveil = "lundi 2h"
regle_de_deux = "[A][C] : lit le web, ses sujets seront publiés. Pas de [B] : lecture des secrets interdite (/proc, .git, dossiers temporaires), jeton du dépôt réservé à l'étape de commit"
secrets = ["CLAUDE_CODE_OAUTH_TOKEN (pour tourner, illisible par la séance)"]
budget = { claude_usd_semaine = 30, appels_gratuits_jour = 0 }
scripts = ["calcul_<sujet>", "son", "planche"]
equipe = []
+++
# Auteur des sujets (atelier)

## Mission
Écrire chaque semaine les nouveaux sujets d'Every Second (règle absurde, vrais calculs, sources vérifiées, scène Remotion), dans les trois langues, avec la prédiction de chacun.

## Entrées
`chaines-studio/atelier/CONSIGNES.md`, le nombre de sujets fixé par le Chef de Contenu, ses retours, les stats des sujets passés.

## Sorties
Sujets complets (json, calcul, son, scène) commités, prédictions dans `atelier/JOURNAL.md`, coût dans `atelier/couts.csv`.

## Outils
Lecture, écriture, recherche web, scripts `calcul_*`, `son`, `planche`, `npm run lint`. Rien d'autre (liste fermée dans atelier.yml).

## Secrets et permissions
Aucun secret lisible. Le contrôle (lint, fichiers requis) passe avant le commit.

## Mesure de réussite
Vues médianes à 7 jours de ses sujets comparées à la médiane de la chaîne. Part de ses prédictions justes. Coût par sujet (2,03 $ équivalent à la première séance, 11/11). Zéro sujet refusé au contrôle.

## Journal
`chaines-studio/atelier/JOURNAL.md`

## Consignes
Celles de `chaines-studio/atelier/CONSIGNES.md`.

## Retours
