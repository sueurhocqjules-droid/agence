# Banc d'essai des modèles gratuits

Mêmes tâches réelles pour chaque modèle (`python -m agents.banc`) : traduire le bloc anglais de « rice » en es et pt (référence : la version validée par Jules), proposer 8 nouveaux sujets avec paliers chiffrés et sourcés, analyser le registre des stats. Réponses brutes et mesures dans chaque dossier daté.

## Verdict du 10/11/2026

| Poste | Retenu | Secours | Pourquoi |
|---|---|---|---|
| Traduction es, pt | Gemini Flash-Lite | Groq qwen3.8-27b | Le plus proche de la version de Jules (« QUEDA 1 SEGUNDO », « CASAS » pour les cases). gpt-oss écrit « EXTIENDIDO » et calque l'ordre anglais |
| Stats | Groq gpt-oss-120b | Gemini Flash-Lite | Tous justes sur les chiffres, gpt-oss-120b le plus rapide. Recommandations génériques chez tous : la décision reste à la Direction |
| Idées de sujets | Gemini Flash | OpenRouter nemotron-3-ultra | Ordres de grandeur et sources plausibles (NASA, USGS, articles). Encore des erreurs (sources floues, échelles mélangées) : chaque sujet passe par le critique avant production. gpt-oss invente ses sources |

Écartés : Cerebras (carte bancaire, 5 $ puis payant), inkling-2-small (interdit en Europe), gemma-4-31b sur OpenRouter (toujours saturé), gemini-2.5-flash (fermé aux nouveaux comptes), gpt-oss-20b (JSON coupé en traduction).

Limites vues : Gemini Flash en 503 et délais dépassés le soir, Groq refuse une demande dont le plafond de sortie dépasse son quota par minute. D'où un secours par poste dans `agence/postes.py`.

À vérifier à l'étape 7 : si l'offre gratuite de Gemini permet la recherche Google intégrée, pour des sources vérifiées sur les sujets.
