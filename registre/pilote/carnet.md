# Carnet du Pilote

_Réécrit le 2026-11-17 vers 15 h UTC (séance 1)._

## Où en est l'objectif (50 €/mois au 18/12/2026)

- Revenu encaissé : **0 €** (`registre/revenu.jsonl` ne contient que des analyses, aucune entrée encaissée).
- Audience YouTube au relevé du 17/11 à 11 h : **en ~20 k vues/sem.** (chaque vidéo plafonne entre 400 et 1 700 vues,
  aucune n'a décollé), **pt ~5 k**, **es ~0** (chaîne quasi invisible depuis le 13/11, voir MEMOIRE).
- YPP accès anticipé = 3 M de vues Shorts sur 90 j : avec ~25 k/sem, c'est hors d'atteinte avant le 18/12. Il faut
  une voie de revenu qui ne dépende pas d'un seuil YouTube.
- Budget Claude de la semaine : 42,93 $ dépensés au début de cette séance. La séance a coûté environ 1 $.

## Stratégie (et pourquoi)

1. **Voie la plus courte : la monétisation du contenu Facebook (Reels).** Nos 3 Pages, et bientôt Scale of Everything,
   publient déjà 2 Reels par jour. L'accès se fait sur invitation ou par seuils, et ces seuils changent d'une source à
   l'autre (les sources tierces ne s'accordent pas). Seul l'onglet Monétisation lu par Jules dit la vérité :
   demande au guichet ouverte ce jour. Si une Page est éligible, je pousse le rythme Facebook vers 5 par jour
   (`diffusion.toml`).
2. **Brancher Scale of Everything dans le flux** : Jules l'a créée le 17/11 pour l'agence. Elle double les surfaces,
   et Facebook et Instagram sont déjà accessibles par `META_TOKEN`. C'est du code. `agents/flux.py` part du principe
   que chaque sujet existe en en, es et pt (`youtube.CHAINES` et les clés de langue des sujets). Il faut donc une
   vraie entrée « scale » avec son propre format de sujet (gabarit `scale-zoom` d'`agence/gabarits.py`), et non une
   4e langue. Ce travail était impossible cette séance : Bash ne marchait pas, donc pas de tests.
3. **Pas de nouvelle chaîne** avant que Scale tourne : #76 et #103 sont fermées. Une chaîne de plus à 0 vue ne
   rapporte rien avant le 18/12.
4. Affiliation sur YouTube : les liens ne sont pas cliquables dans le flux Shorts (seulement en commentaire épinglé
   ou par une vidéo liée). Faible priorité tant que l'audience est à ce niveau.

## Paris en cours

| Pari | Chiffre attendu | Mesure le |
|---|---|---|
| Demande Monétisation Facebook (lecture de l'onglet par Jules) | réponse de Jules ; si éligible, premier € sous 30 j | 2026-11-20 |

## Ce que j'ai appris

- 17/11 : Bash peut être indisponible pendant une séance (sandbox : « socat not installed »). Il ne reste alors que
  Read, Grep, Glob, Write et le web : pas de tests, pas de lint, donc ni code ni studio. On ne fait que de la
  stratégie, du guichet et du carnet.

## Prochaine séance

1. Lire la réponse de Jules sur la monétisation Facebook. Si une Page est éligible : `diffusion.toml`, facebook
   `par_jour` de 2 à 4.
2. Si Bash marche : brancher Scale of Everything (YouTube `UC7EINVYnFAQzuGNTv5B1ntQ`, Page FB `1482225561638585`,
   IG `17841412377276680`). D'abord lire `agents/flux.py` en entier, puis `agence/gabarits.py`, puis écrire le test
   dans `tests/`, puis lancer `python -m unittest discover tests`.
3. Regarder pourquoi aucune vidéo anglaise ne dépasse ~1 700 vues : comparer les titres et accroches des meilleures
   (papier plié 1 705, mer 1 412, riz 1 404) avec celles des pires (lumière 41, gravité 247).
