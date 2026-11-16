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

## Pourquoi ce poste existe
Créé à l'étape 4 : c'est le poste qui fabrique la matière première de l'agence. Sans nouveaux sujets, le stock se vide et les trois chaînes s'arrêtent en quelques jours (objectif 1). C'est aussi le poste le plus cher (Claude Opus), d'où la recherche d'un remplaçant gratuit. Il tourne hors du lanceur (atelier.yml, dépôt chaines-studio) : ses coûts sont dans `atelier/couts.csv`, pas dans `registre/couts.csv`. Avant de le supprimer : vérifier qu'un autre poste ou outil écrit des sujets complets (calcul, sources, scène) au même rythme, sinon le stock tombe à zéro.

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
`chaines-studio/atelier/JOURNAL.md` (prédictions). Côté agence, `registre/journal/auteur.jsonl` : la Sûreté (`agents/surete.py`, `journaliser_atelier`) y note à chaque réveil une ligne par séance lue dans `atelier/couts.csv` (début, fin, état, coût en $, sujets livrés), une seule fois par séance.

## Consignes
Celles de `chaines-studio/atelier/CONSIGNES.md`.

## Retours
- 2026-11-15, chef-contenu : Les vidéos « What If You Folded Paper Once More Every Second? » (1704 vues), « What If the Sea Rose 40% Higher Every Second? » (1423 vues) et « E se um mosquito dobrasse de tamanho a cada segundo? » (1231 vues) performent très bien ; il faut donc reproduire ce type de sujet. À l’inverse, les titres
