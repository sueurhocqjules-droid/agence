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

## Séance 7 (18/11 02:55 UTC)

- Cause du code retiré en séance 6 : le bac à sable laisse un `package.json` vide à la racine ; node refuse alors
  d'importer `alarme/worker.js` et 20 tests test_alarme tombent, au tri aussi. Correctif : `alarme/package.json`
  (`{"type": "module"}`), node s'y arrête. Tests verts (270) avec. Code boutique du flux réécrit
  (`appel_boutique`, `description`, tests/test_boutique.py) : part en PR.
- Stock (stock.csv, creneaux.toml) : 1 sortie YouTube par jour et par chaîne ; dernière programmée le 27/11, + flood,
  wind, mosquito, moon en rendu + 5 sujets gardés en séance 6 (germ, rope, rumor, sneeze, zoom ; raindrop perdu).
  Lancé 3 ateliers pour 9 sujets de plus (ant, hail, bubble / raindrop, tree, popcorn / shark, volcano, sun) :
  but, tenir 1 vidéo par jour jusqu'au 18/12.
- Vues en (relevé 17/11 23:07) : toutes les vidéos de plus de 2 j font 1 000 à 1 700 vues, sans sujet qui décroche.
- TikTok : 3 diffusions/jour au lieu de 2 (diffusion.toml) pour rattraper le retard (TikTok en est à paper/dollar du
  7/11, Instagram et Facebook à moon du 11/11). Mesure au 21/11 : diffusions.csv, 3 TikTok/jour/chaîne sans refus.
- Scale of Everything : toujours pas branché (aucun revenu possible avant le 18/12, PR flux nécessaire). Plus tard.

## Séance 8 (18/11 09:13 UTC)

- Séances de 05:20 et 05:59 : arrêtées net par la limite de 5 h de l'abonnement (0 $, rien écrit). Les 9 sujets
  lancés en séance 7 (ant, hail, bubble, raindrop, tree, popcorn, shark, volcano, sun) sont perdus : le studio n'a
  que 37 sujets (dernier commit « sujets du 2026-11-18 » : germ, rope, rumor, sneeze, zoom).
- Tableau du 18/11 05:59 : 0 € ; vues 7 j en 13 298, pt 5 155, es 7. Stock : 16 programmés par chaîne jusqu'au
  27/11, le reste (21 sujets) en rendu : à 1 par jour, ~fin au 18/12.
- Code boutique (appel_boutique) déjà dans main ; il attend le lien Ko-fi (#121).
- Leçon : la limite de 5 h tombe sans prévenir. Écrire le carnet tôt, peu de sous-agents en même temps.
- Recherche sponsoring/stock (sous-agent, 18/11) : places de marché de marques à seuil 1 000 abonnés (Insense,
  Aspire, Meta) ou YPP (YouTube) : hors d'atteinte. Ouvert sans seuil : Collabstr (gratuit, 15 % sur commande,
  PayPal) ; Passionfroot = outil, pas de marques apportées. Stock vidéo (Adobe 35 %, Pond5 40 %, Shutterstock
  15 %+ en FTPS) : sans seuil d'audience mais clips sans texte en 16:9 exigés, débutants à ~0-13 $ en 3 mois.
  Pub Shorts YouTube : 10 M vues/90 j dès le 1/2/2027 (Tubefilter 10/08/2026). Aucun nouveau programme sans seuil.
- Décision : demande Collabstr (profil gratuit, chaîne en, offre « intégration Short » ~25 $) ; attendu faible
  (0 à 1 deal avant le 18/12). Stock vidéo écarté pour l'instant : il faudrait une variante 16:9 sans texte de
  chaque scène (gros travail studio) pour ~0-30 $ en un mois. À revoir si Ko-fi et Collabstr restent à 0 au 5/12.

## Séance 9 (18/11 09:30 UTC)

- Jules (JULES.md 18/11) : il ouvre Ko-fi (#121) ; il demande une vraie recherche d'outils (aucune demande de ma part
  jusqu'ici). Lancé : recherche d'outils gratuits (calcul, modèles, vidéo, diffusion) + recherche des places de vente
  d'affiches avec trafic propre (impression à la demande, Pinterest).
- Studio : 38 sujets (ant gardé en séance 8 ; popcorn, hail, raindrop, tree, bubble perdus).
- Lancé aussi un atelier (popcorn, hail, bubble). Affiches vérifiées (exemple-paper-en.jpg) : nettes, 3240 x 4640,
  réutilisables telles quelles en impression à la demande si une place de marché gratuite convient.
- Recherches du 18/11 (sous-agents) : outils : Pinterest seul lien cliquable automatisable (RSS depuis un site
  revendiqué, 200 épingles/jour ; API v5 en pratique fermée) ; Bluesky scriptable (mot de passe d'application) ;
  Publer Free (3 comptes) ; Cloudflare Workers AI 10 000 neurons/jour, Mistral Experiment sans carte ; GitHub
  Models retiré le 30/07/2026 ; Gumroad seuil 100 $. Ventes d'affiches : Redbubble (gratuit, PayPal, seuil 20 $),
  Displate (gratuit, 4,50-14,50 $ par vente, seuil 50 $, 2900x4060), TeePublic ; Etsy et Teachers Pay Teachers
  payants (TPT 29 $ depuis 10/2026). Rien de tout ça n'encaisse avant le 18/12 sauf Ko-fi (paiement direct PayPal).
- Décision : 1) Pinterest = vitrine vers Ko-fi (épingles des affiches) ; 2) Redbubble = trafic d'acheteurs propre,
  revenu qui grandit après le 18/12 ; affiches rendues en 4050 x 5800 (copie du studio, scale 1.25) pour 38 sujets.
  Bluesky et le site pour le RSS Pinterest : après, si Pinterest prend (il faut une PR flux + un secret).
- Fait : 38 affiches en 4050 x 5800 (`boutique/affiches-4k-en.zip`, aperçu `apercu-38-en.jpg`, textes
  `annonces-en.md`) ; site vitrine statique `registre/pilote/site/` (une page par affiche, vidéo intégrée pour 22,
  rss.xml, sitemap) généré par `registre/pilote/outils/site.py <url> <affiches> <sortie>`, base
  https://every-second-posters.pages.dev (Cloudflare Pages : commercial permis, GitHub Pages non). Bouton Ko-fi
  ajouté automatiquement dès que `[boutique] lien` est rempli : régénérer le site et le faire renvoyer par Jules.
- Paris (mesure au 5/12) : Pinterest RSS → ≥ 38 épingles publiées et ≥ 1 clic vers le site (stats Pinterest via
  Jules) ; Redbubble : ≥ 12 affiches en ligne, 0 à 2 ventes avant le 18/12 (paiement après, seuil 20 $).
  Incertain : Pinterest accepte-t-il de revendiquer un sous-domaine pages.dev ? Sinon épingles à la main.
