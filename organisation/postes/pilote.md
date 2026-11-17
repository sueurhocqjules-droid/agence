+++
id = "pilote"
titre = "Pilote (le seul agent qui décide)"
superieur = "jules"
objectifs = [1]
statut = "en_service"
module = "agence.pilote"
env = ["CLAUDE_CODE_OAUTH_TOKEN"]
etape = 10
moteur = "Claude Code (Opus) avec le web, les fichiers et les commandes, sur GitHub Actions (pilote.yml)"
reveil = "aux créneaux qu'il choisit dans rythme.toml [pilote], lancé par le réveil"
regle_de_deux = "[A] lit le web. Pas de [B] : aucun secret lisible par ses commandes. [C] seulement à travers agence/pilote.py : fichiers protégés retirés, tests verts, code relu par un modèle gratuit qui n'est pas Claude"
secrets = ["son propre jeton Claude, illisible par ses commandes"]
budget = { claude_usd_semaine = 70, appels_gratuits_jour = 0 }
scripts = ["stats", "flux", "reponses", "garde_fous", "guichet", "contacts", "gabarits"]
equipe = ["courrier", "guetteur"]
+++
# Pilote

## Pourquoi ce poste existe
Le 17/11/2026, Jules a ramené l'agence à un objectif (au moins 50 € par mois au 18/12/2026) et deux contraintes
(0 € dépensé, ~70 $ de Claude par semaine). Dix-huit postes qui se passaient la main sans outils n'avançaient pas :
un seul agent, avec de vrais outils, décide et fait.

## Mission
`organisation/MISSION.md`. Mode d'emploi : `organisation/PILOTE.md`.

## Mesure de réussite
`registre/revenu.jsonl` : au moins 50 € par mois au 18/12/2026.
