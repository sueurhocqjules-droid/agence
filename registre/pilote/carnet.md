# Carnet du Pilote

_Réécrit le 2026-11-17 vers 23 h UTC (séance 5, en cours)._

## Où en est l'objectif (50 €/mois au 18/12/2026)

- Revenu encaissé : **0 €** (`registre/revenus.csv` vide, tableau du 17/11 22:39).
- YouTube (relevé du 17/11 17:07) : en 13 125 vues gagnées en 7 j, pt 5 078, **es 6** (30 vidéos, chaîne morte).
- Stock : 30 vidéos par chaîne programmées jusqu'au 25/11 environ ; balloon et candle en rendu. Ensuite plus rien
  si aucun sujet n'est écrit (32 sujets dans le studio).
- Monétisation Facebook (relevé de Jules, PILOTE.md) : pas éligible (invitation seulement). Pari du 17/11 clos : négatif.

## En cours dans cette séance

- Recherche des voies de revenu à 0 € (sous-agent), pour choisir la voie avant d'écrire du code.
- Scale of Everything : le réveil n'a ni node ni Remotion ; seul studio-rendu rend, et seulement les sujets du
  studio (compositions `Sujet-Langue`). Brancher Scale = soit des sujets du studio avec une clé `scale`, soit un
  rendu des gabarits `remotion/` à ajouter quelque part. À décider après la recherche.

## Séance 6 (18/11 02:27 UTC)

- Tableau du 17/11 23:11 : 0 € ; vues 7 j en 13 185, pt 5 141, es 6. Stock programmé jusqu'au 27/11 (candle),
  flood/wind/mosquito/moon en rendu : ~4 jours de plus. Recherche des voies de revenu relancée (sous-agent).
- Stock : les 32 sujets du studio sont tous programmés ou en rendu ; dernière sortie prévue candle le 27/11.
  Lancé 6 sujets neufs (rumor, sneeze, rope, germ, zoom, raindrop) par 2 sous-agents, style « objet du quotidien qui
  croît chaque seconde » (les meilleurs en : paper 1 706, flood 1 411, rice 1 404, mosquito 1 352 vues au 17/11).
- Scale of Everything : non branché cette séance. Brancher = PR sur agents/flux.py (Oui de Jules) pour une chaîne
  neuve qui ne rapportera rien avant le 18/12 ; passe après la voie de revenu.
- Recherche revenus (sous-agent, 18/11) : aucune voie sûre vers 50 €/mois au 18/12. Programmes des plateformes hors
  d'atteinte (YouTube : 3 M vues Shorts/90 j, et dès le 1/2/2027 20 M ; TikTok 10 k abonnés ; Facebook sur invitation).
  Seule voie sans seuil : vente directe ou dons (Ko-fi : 0 % sur dons, 5 % boutique ; Payhip 5 %). Stock footage :
  seuil 25 $, des mois avant une vente. Amazon : paiement à J+60, trop tard.
- **Pari du 18/11** : boutique Ko-fi (dons + 2 packs de 12 affiches 4K, en et pt, prix libre dès 3 €). Fait : packs
  dans `registre/pilote/boutique/` (rendus par `chaines-studio/scripts/affiches.py`), lien réglable
  `[boutique]` de diffusion.toml + code du flux (PR). Attendu : ≥ 1 € (vente ou don) avant le 18/12, 0 à 3 ventes/mois.
  Mesure : 18/12 dans revenus.csv. Dépend de Jules (compte Ko-fi + PayPal).
- Environnement : un package.json vide à la racine (posé par le bac à sable) casse le bundle Remotion et les tests
  test_alarme en local. Rendu fait depuis une copie du studio dans $TMPDIR (node_modules copié, pas lié).
