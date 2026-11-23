# agence

Plomberie de la machine à contenu Every Second : outils de publication, stats, sûreté et liens avec Jules. Aucun agent Claude ici depuis le 23/11/2026 (le Pilote et la couche v2 ont été retirés). La fabrication des vidéos vit dans `chaines-studio`, le plan dans `jarvis-starter-kit/livrables/business/machine-a-contenu/README.md`.

## Structure

| Chemin | Rôle |
|---|---|
| `.github/workflows/reveil.yml` | Réveil sur GitHub, PC éteint, aux heures de `organisation/rythme.toml` (lancé par le Worker de l'alarme, cron en filet). Une étape par script, avec ses seuls secrets, puis commit du registre |
| `.github/workflows/reponses.yml` | Lit tout de suite un clic Oui/Non de Jules sur Telegram (lancé par le Worker) |
| `agence/lancer.py` | Lanceur unique (`python -m agence.lancer <nom>`) : pause, budget, journal, clés accordées |
| `agence/meta.py`, `buffer.py`, `threads.py`, `youtube.py` | Publication et lecture : Instagram et Facebook (Meta), TikTok (Buffer), Threads, YouTube |
| `agents/flux.py` | Rendu, contrôle, programmation YouTube et diffusion sur les autres réseaux |
| `agents/diffusion.py` | Publie `organisation/planning-diffusion.csv` sur Instagram, Facebook et TikTok. Base du futur workflow de diffusion commun |
| `agents/stats.py`, `surete.py`, `courrier.py`, `guetteur.py` | Stats des chaînes, garde-fous (seuils, pauses, alertes), tri de la boîte mail, seuils de monétisation |
| `agence/questions.py`, `telegram.py`, `alarme.py`, `alarme/` | Questions Oui/Non à Jules, alertes Telegram, alarme hors de GitHub (Worker Cloudflare) |
| `agence/guichet.py`, `contacts.py` | Demandes à Jules (issues `guichet`) et messages à des personnes, envoyés après validation (issues `contact`) |
| `organisation/` | Réglages : `scripts.toml` (scripts et leurs clés), `autorisations.toml` (quelle clé va à qui, protégé), `seuils.toml`, `rythme.toml`, `creneaux.toml`, `diffusion.toml`, `MEMOIRE.md` (leçons apprises) |
| `registre/` | Mémoire versionnée, en ajout seul : stock, stats, diffusions, coûts, pauses, questions, journaux. Colonnes dans `registre/README.md` |
| `ressources/` | Catalogue des outils, boutique Ko-fi (affiches) |

## Pauses

La dernière ligne d'une cible dans `registre/pauses.csv` fait foi. Au 23/11, `stats`, `flux`, `guetteur`, `courrier`, `contacts`, `guichet` et `gabarits` sont en pause (arrêtés avec le Pilote le 18/11), en attendant la décision de Jules. Tournent : `diffusion`, `reponses`, `garde_fous`.

## Règles

- **Secrets** : jamais dans le dépôt. Secrets d'Actions GitHub, transmis par le lanceur seulement s'ils sont déclarés dans `scripts.toml` (ou la fiche du poste) **et** accordés dans `autorisations.toml`
- **Le registre ne se réécrit pas** : on ajoute des lignes

## Lancer en local

```powershell
pip install -r requirements.txt
$env:PYTHONUTF8 = "1"; python -m unittest discover tests
```
