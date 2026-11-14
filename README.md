# agence (nom provisoire)

Entreprise de contenu menée par des agents : scripts pour le routinier, modèles gratuits pour le texte, Claude réveillé rarement pour trancher. Jules est l'actionnaire : un mail le lundi, des boutons Oui/Non sur Telegram. Plan et objectifs : `jarvis-starter-kit/livrables/business/machine-a-contenu/README.md`.

## Structure

| Chemin | Rôle |
|---|---|
| `agence/` | Code partagé : `registre.py` (lecture et écriture du registre, coût de chaque passage), `youtube.py` (accès aux chaînes) |
| `agents/` | Un fichier par agent, lancé par `python -m agents.<nom>` |
| `registre/` | Mémoire commune versionnée : stock, stats, coûts, décisions. Colonnes dans `registre/README.md` |
| `chaines-studio/scripts/synchro_rendu.py` (déplacé le 11/11) | Copie le moteur de rendu de `chaines-studio` vers le dépôt public `studio-rendu`, liste blanche seulement (ni jetons, ni publication, ni nightworks) |
| `ressources/catalogue.md` | Ce que l'agence a le droit d'utiliser, avec coût et accord nécessaire |
| `ressources/boite-a-outils-jarvis.md` | Copie de la boîte à outils de Jarvis, envoyée par le hook de fin de session de Jarvis (`.claude/hooks/boite-vers-agence.sh`) dès qu'elle change. Lue par le seul Chercheur d'outils, ne pas modifier ici |
| `.github/workflows/reveil.yml` | Réveil programmé sur GitHub, PC éteint, qui commite le registre |
| `.github/workflows/ingenierie.yml` | Ingénierie : une issue étiquetée `ingenierie` (posée par Jules, ou écrite par un agent avec `agence.ingenierie.demander`) devient une PR écrite par Claude Code, 40 tours et 3 $ au plus. Le script lance les tests, le banc, le contrôle des fichiers protégés et la relecture, puis fusionne seul si tout est vert. Fichier protégé touché : la PR attend Jules avec l'étiquette `guichet`. Reprise sans Claude d'une PR restée ouverte : `gh workflow run ingenierie.yml -f pr=<n>` |
| `agence/guichet.py` | Le guichet : seul module par lequel un agent demande à Jules ce que l'agence ne peut pas faire seule (compte, dépôt, clé, machine). `guichet.demander(...)` ouvre une issue `guichet` au format fixe (quoi, pourquoi, lien, ce que ça débloque, coût), `urgent` en plus si ça bloque. Récapitulatif Telegram une fois par jour (`python -m agence.lancer guichet recap`, dernière étape du réveil). État : `python -m agence.guichet` |
| `organisation/autorisations.toml` | Quelle clé va à quel poste ou script. Fichier protégé : seul Jules l'élargit. Le lanceur ne transmet une clé que si elle est déclarée par la fiche ou le script **et** accordée ici |
| `agence/contacts.py` | Contacts avec des personnes : `contacts.preparer(...)` met un message en attente (issue `contact`), il part au réveil qui suit la pose de l'étiquette `valide` par le compte de Jules, signé par l'équipe de la chaîne. L'envoi demande `GMAIL_SEND_TOKEN` (droit `gmail.send` seul) : tant qu'il manque, rien ne part |
| `.github/workflows/protege.yml` | Fichiers protégés (règle 9) : PR rouge si elle touche `.github/`, `MISSION.md`, les autorisations de clés, le contrôle ou un test / cas de banc existant, sauf étiquette `accord-jules` posée par Jules (`agence/protege.py`). Relecture de chaque PR par Gemini en commentaire (`agence/relecture.py`) |

## Règles de construction

- **Un agent = une commande** et une `registre.seance("<nom>")` qui écrit son coût, même en cas d'échec. C'est ce qui permettra de brancher Paperclip plus tard (adaptateur « processus maison ») sans rien réécrire
- **Le registre ne se réécrit pas** : on ajoute des lignes. Une décision note sa prédiction et la mesure qui la jugera, le verdict revient au critique
- **Secrets** : jamais dans le dépôt. Sur GitHub, en secrets d'Actions (`YT_TOKEN_EN`, `YT_TOKEN_ES`, `YT_TOKEN_PT`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, `RENDU_DEPLOY_KEY` : clé SSH en écriture sur `studio-rendu` seulement). En local, `agence/youtube.py` lit les jetons de `chaines-studio/.secrets/`
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
| `flux` | Compare les sujets du moteur (`studio-rendu`) aux vidéos des chaînes. Ce qui manque part en rendu (file `studio-rendu/file/attente.txt`), ce qui est rendu est contrôlé (`agence/controle.py` : durée, format, son, écran noir) puis programmé au prochain créneau (en 01h/18h, es 02h/19h, pt 16h/23h, Paris). `--essai` pour voir sans agir. Ne crée pas de sujet : un nouveau sujet s'écrit dans `chaines-studio`, puis `scripts/synchro_rendu.py` de `chaines-studio` (l'atelier le fait seul, `chaines-studio/.github/workflows/atelier.yml`) | 0 jeton, ~1 600 unités de quota par envoi |
| `banc` | Banc d'essai des modèles gratuits sur les vrais postes (local, lit `../chaines-studio`). Verdict : `banc/README.md` | 0 jeton, ~30 appels gratuits |
