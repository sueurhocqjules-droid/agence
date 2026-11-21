# Explication en 3D (« comment ça marche », « et si… »)

**Statut : passe** (relevé du 19/11/2026). Premier format à tester.

## Le format

- **Recette** : une question posée dès la première seconde, puis la réponse montrée pas à pas en 3D, avec une voix off
  et des sous-titres mot à mot. Chiffres affichés à l'écran (volumes, vitesses, comparaisons).
- **Deux variantes du même moule** : « comment ça marche ou se construit » (cale sèche, canal, panier de basket) et
  « et si… » absurde et chiffré (toutes les flatulences d'une vie en une seconde, Kawhi Leonard contre la Grande
  Muraille). Le sujet et l'accroche changent, la fabrication et la structure restent.
- **Durée** : 50 à 100 s (35 : 70 s, 22 : 56 s, 21 : 89 s, 40 : 98 s).
- **Accroche** : la question en voix off sur la première image (« If you dig a hole next to the sea, you can park a
  ship in it », « What if every fart you've ever done came out at once? »).
- **Son** : voix off de synthèse en anglais, musique d'ambiance légère, bruitages.
- **Style** : 3D cartoon simple (whatifbagel, whatifmerchant, Zack D. Films) ou 3D semi-réaliste propre
  (mildly.elsewhere, wemakebuild, builtfromscraps_).

## Fabrication à 0 €

- **Oui, à tester.** 3D codée en three.js : `@remotion/three` (module officiel de Remotion, règle dans le skill
  `remotion-best-practices/remotion-markup/3d.md`), ou le dépôt
  [claude-animation-skills](https://github.com/artemnovitckii/claude-animation-skills) (MIT, 951 étoiles au 19/11,
  skills `/zach-d-films` et `/breakdown`, voix gratuite en local ; prévu pour macOS et Linux, à tester sous Windows).
- Personnages et objets : modèles low-poly sous licence CC0 (Quaternius Universal Base Characters, Kenney Blocky
  Characters), à vérifier dans le fichier de licence de chaque pack.
- Brism (49 $/mois) vend exactement ça : Claude Code qui écrit, fait la voix et anime en local. Preuve que la
  fabrication par code tient ce style.
- Point dur : la variante semi-réaliste (eau, terrain, engins) demande plus de travail que la variante cartoon.
  Commencer par la cartoon.

## Vidéos de référence

| Vidéo | Compte | Vues | Médiane du compte (> 3 j) | Écart |
|---|---|---|---|---|
| [35](https://www.instagram.com/p/DfxG0oMDSvm/) cale sèche | mildly.elsewhere | 4,76 M | 987 324 | x4,8 |
| [22](https://www.instagram.com/p/De4WwrdvOOF/) Kawhi contre la Grande Muraille | whatifbagel | 3,55 M | 368 366 | x9,6 |
| [21](https://www.instagram.com/p/DfVuOh7x02S/) flatulences | whatifmerchant | 21,7 M | 52 924 | x410 |
| [40](https://www.instagram.com/p/Deiz8tguWYI/) canal | wemakebuild | 30,7 M | 195 462 | x157 |
| [41](https://www.instagram.com/p/DeslQ1oAgT3/) panier de basket | builtfromscraps_ | 7,2 M | 80 640 | x89 |
| [19](https://www.instagram.com/p/DdJeKdhDOt_/) marathon en ver de terre | zackdfilms | 8,7 M | 3,75 M | x2,3 |

## Comptes qui le font (médiane des 10 dernières vidéos de plus de 3 j / abonnés)

- Au-dessus du seuil : mildly.elsewhere 987 324 / 20 803 ; baydarfilms_ 752 831 / 49 336 ; whatifbagel 368 366 / 58 122.
- Sous le seuil : wemakebuild 195 462 / 123 693 (x1,6) ; whatifmerchant 52 924 / 36 354 ; builtfromscraps_ 80 640 /
  126 231 ; zackdfilms 3,75 M / 11,57 M (l'original, compte géant).

## Saturation et ancienneté

- Format lancé par Zack D. Films, copié depuis par beaucoup de comptes. Il reste de la place : wemakebuild a commencé
  le 16/10/2026 et fait déjà 195 000 vues de médiane avec 27 vidéos.
- Brism et claude-animation-skills le rendent facile à fabriquer : la concurrence va grossir. Le sujet et l'accroche
  feront la différence.

## Essais

- **20/11, test 1 : « What if you cloned yourself every second » (Every Second, anglais, 39,5 s).** Fichier :
  `chaines-studio/3d/clones/out/final.mp4` (1080x1920). Moteur : claude-animation-skills (three.js rendu par
  Playwright, 1 186 images à 0,4-2 s chacune), voix Kokoro am_michael, sous-titres mot à mot (Parakeet),
  compteur en haut, 10 plans (héros, poof, salle de concert, ville, Terre, foule serrée, balance, boule, lumière,
  boucle finale). Son : musique « Pizzicato » d'Ehma (Jamendo, CC BY, crédit dans `audio/music/CREDITS.md`),
  bruitages du kit earshot (preset launch) calés sur les cuts et les événements, script `audio/mix.py`.
  Mesures earshot : -14,6 LUFS (référence whatifbagel -14,2), 85 % des 73 repères son à moins de 40 ms
  (hasard 45 %). Même palette musicale que la référence selon earshot (pizzicato, fond « corporate »).
  Écarts connus : 39,5 s contre 50-100 s dans la recette ; un plan toutes les 2,2 s contre 1,8 s chez la
  référence ; Terre en taches et non en continents ; whoosh de la Terre (0:12) masqué par la voix.
  Avis de Jules (20/11) : très satisfait, concept à fort potentiel, il serait resté devant. Voix, musique et
  volume, sous-titres, durée (un peu courte mais adaptée au format), rythme, bruitages, décalage de 178 ms et
  Terre en taches : tout validé. Seul défaut : le personnage (« mains trop loin, tête un peu bizarre, corps long,
  pas de pieds »), et l'envie qu'il soit plus original puisqu'on le voit en premier. Corrigé le jour même dans
  `src/human.js` (pieds qui étaient sous le sol, mains rattachées, torse et jambes plus courts, tête cartoon d'un
  seul bloc sans barbe, grands yeux, sourire, t-shirt sans rayures). Labo de personnage : `node render.mjs lab
  <nom>-<vue>[@t] out/lab` (`src/lab.js`, `@t` = instant du chrono). Trois signatures proposées (chrono,
  casquette et lunettes, cheveux bleus) : Jules garde **le chrono seul**, les deux autres ajoutent des pièces qui
  ratent (branches de lunettes pas raccordées). Retour du 20/11 au soir : corps long gardé (« ça lui donne un
  style »), mains à l'envers corrigées (moufle, paume vers la cuisse, pouce vers le bas). **Signature du héros
  d'Every Second** : chronomètre noir imprimé à plat sur le t-shirt orange (bouton et aiguille rouges) et grosse
  montre noire au poignet gauche (cadran blanc, cercle et aiguille rouges). L'aiguille fait deux tours rapides au
  lancement, puis avance d'un sixième de tour par seconde (`chronoAngle` dans `human.js`, piloté par le temps du
  film). Idée de Jules : ces éléments font l'identité, le personnage peut changer de tenue et rester reconnaissable.
  Foule de clones remise aux nouvelles proportions, avec l'imprimé et la montre. Flash du « poof » corrigé (il
  coupait les corps en deux sur le plan final, défaut présent depuis le début).
  Piste pour plus tard (Jules) : rendre le personnage interactif, les gens choisissent un détail en commentaire
  (ex. ses chaussures : « hot-dog ») et il le porte dans la vidéo suivante.

- **20/11 au soir, test 2 (nuit parallèle sur le ZBook, essai pour utiliser des jetons restants, hors plan) :**
  10 vidéos Every Second faites sans Claude à la main (jump, taller, sneeze, hair, shrink, skyscraper, eat, et 3
  sujets libres de l'agent : battery, heavy, bright), 35 à 44 s, programmées du 23/11 au 28/11. Registre :
  `chaines-studio/3d/registre.csv`, rapport : `chaines-studio/nightwork/2026-11-20/RAPPORT.md`.
  Avis de Jules (21/11, échantillon tiré au hasard : sneeze, shrink, skyscraper, battery, bright) : plutôt
  satisfait, publiées telles quelles (chaînes de test, on verra l'impact des défauts). Aimé : les touches
  d'humour, les comparaisons concrètes (ingénieurs, « plus de puissance qu'une TNT ») qui rendent intéressant un
  concept qu'il trouvait banal au départ, le mot de la fin. Moins bien : `bright`, le plus faible (moins de
  recherche, moins entraînant), gardé pour voir ses vues. **Retours pour l'évolution du format, pas à faire
  tout de suite :**
  - Arrière-plan toujours bleu : le faire varier (couleur, soleil qui se lève ou se couche), décor un peu plus
    fourni autour du personnage
  - Personnage raide « comme un bâton » : plus de mouvement, et des expressions faciales
  - Variété du personnage : couleur des habits, et peut-être couleur de peau et origine (plus subjectif)
  - Plus de détails, d'interactions et d'action pour stimuler l'œil
  - Défauts de collision : la main traverse le téléphone (battery, bright), la batterie qui grossit traverse
    l'écran (battery)
