# agence (nom provisoire)

Entreprise de contenu menée par des agents : scripts pour le routinier, modèles gratuits pour le texte, Claude réveillé rarement pour trancher. Jules est l'actionnaire : un mail le lundi, des boutons Oui/Non sur Telegram. Plan et objectifs : `jarvis-starter-kit/livrables/business/machine-a-contenu/README.md`.

## Structure

| Chemin | Rôle |
|---|---|
| `agence/` | Code partagé : `registre.py` (lecture et écriture du registre, coût de chaque passage), `youtube.py` (accès aux chaînes) |
| `agents/` | Un fichier par agent, lancé par `python -m agents.<nom>` |
| `registre/` | Mémoire commune versionnée : stock, stats, coûts, décisions. Colonnes dans `registre/README.md` |
| `ressources/catalogue.md` | Ce que l'agence a le droit d'utiliser, avec coût et accord nécessaire |
| `.github/workflows/reveil.yml` | Réveil programmé sur GitHub, PC éteint, qui commite le registre |

## Règles de construction

- **Un agent = une commande** et une `registre.seance("<nom>")` qui écrit son coût, même en cas d'échec. C'est ce qui permettra de brancher Paperclip plus tard (adaptateur « processus maison ») sans rien réécrire
- **Le registre ne se réécrit pas** : on ajoute des lignes. Une décision note sa prédiction et la mesure qui la jugera, le verdict revient au critique
- **Secrets** : jamais dans le dépôt. Sur GitHub, en secrets d'Actions (`YT_TOKEN_EN`, `YT_TOKEN_ES`, `YT_TOKEN_PT`). En local, `agence/youtube.py` lit les jetons de `chaines-studio/.secrets/`
- **0 € tant que l'agence ne gagne rien**

## Lancer en local

```powershell
pip install -r requirements.txt
python -m agents.stats
```

## Agents

| Agent | Fait | Coût |
|---|---|---|
| `stats` | Relève vues, likes, commentaires de chaque vidéo des trois chaînes | 0 jeton, ~10 unités de quota YouTube |
