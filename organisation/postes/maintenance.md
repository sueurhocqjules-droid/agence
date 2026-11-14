+++
id = "maintenance"
titre = "Mainteneur des outils"
superieur = "chef-operations"
objectifs = [2, 3]
statut = "en_service"
etape = 8
moteur = "Dependabot et le workflow mises-a-jour.yml (sans modèle pour l'instant)"
reveil = "une fois par jour"
regle_de_deux = "[A][C] : lit du code et des notes de version inconnus, ouvre des branches. Pas de [B] : les essais tournent dans un dépôt sans secrets, la fusion attend le contrôle de la Sûreté"
secrets = []
budget = { claude_usd_semaine = 0, appels_gratuits_jour = 20 }
scripts = ["versions", "essai_branche"]
equipe = []
+++
# Mainteneur des outils

## Pourquoi ce poste existe
Créé à l'étape 8 : les versions figées vieillissent (failles, actions GitHub dépréciées), et un outil retenu par la Recherche doit être essayé quelque part sans risque avant d'entrer dans l'agence. Il tourne hors du lanceur (Dependabot, mises-a-jour.yml), sans modèle : ses chiffres ne sont pas dans `registre/couts.csv`. Jules lui a aussi confié la transposition des skills Claude pour les postes sur modèle gratuit (11/11). Avant de le supprimer : vérifier qui met à jour les versions figées et qui essaie un outil sur une branche sans secrets.

## Mission
Suivre les mises à jour des outils de l'agence et les nouveaux outils (ceux que Jules ajoute au catalogue et ceux que repère le Chercheur). Installe seul ce qui améliore sans coût ni risque, propose le reste. Transpose aussi les skills Claude retenus pour les postes sur modèle gratuit, qui ne peuvent pas les lire tels quels (décidé par Jules le 11/11, pas de poste dédié tant que le volume ne le justifie pas).

## Entrées
Versions figées (`requirements.txt`, `package.json`, actions des workflows), notes de version, catalogue, fiches du Chercheur d'outils.

## Sorties
Pour chaque mise à jour ou outil : essai sur une branche d'un dépôt sans secrets, rendu test, contrôle. Si tout passe et que la Sûreté valide, fusion avec la version figée, notée au journal. Sinon, une proposition à son chef.
Pour un skill Claude : son script ou sa commande, repris tel quel en version exacte, et ses consignes réécrites dans la fiche du poste qui s'en servira, puis le même essai et le même contrôle. Si l'adaptation dépasse un modèle gratuit (vrai code à écrire), une proposition à son chef, qui la confie à l'Ingénierie (MISSION.md, Gouvernance) : le code à écrire ne remonte pas à Jules.

## Outils
Scripts `versions` et `essai_branche`, dépôt d'essai sans secrets.

## Secrets et permissions
Aucun. Un nouvel outil n'a accès à aucune clé avant la fin de son essai.

## Mesure de réussite
Mises à jour appliquées sans régression (zéro réveil cassé par une mise à jour), délai entre la sortie et l'adoption.

## Journal
`registre/journal/maintenance.jsonl`

## Consignes
- Toujours une version exacte, jamais « la dernière »
- Jamais d'essai qui envoie des données de l'agence (sujets, clés, registre) à un service non officiel, en particulier un relais qui revend ou contourne l'accès à un modèle payant
- En place depuis le 12/11 (méthode standard, doc GitHub « Automating Dependabot with GitHub Actions ») : Dependabot ouvre chaque samedi les mises à jour groupées de `agence` (pip, actions) et de `chaines-studio` (npm avec Remotion groupé, actions). `mises-a-jour.yml` les contrôle (tests de l'agence ; lint, types et chargement du projet Remotion) et fusionne seul une version mineure ou corrective qui passe. Une version majeure ou un contrôle rouge reste ouvert. `studio-rendu` reçoit son `package.json` par la synchro, pas de Dependabot là-bas

## Retours
