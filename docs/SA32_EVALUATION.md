# SA-32 — Jeu de questions et protocole d'évaluation des LLM

**État : livrable préparé et testé statiquement ; campagne réelle à exécuter sur le PC équipé de Qwen3.5 4B.**

## 1. Périmètre exact (backlog SA-32)

Objectif : produire un jeu de questions **reproductible et structuré** pour évaluer le dialogue d'orientation SmartCampus AI (IIT/ISB) en français, dialecte tunisien, Arabizi et code-switching. Le corpus reflète les exigences de `Projet_IAG_p3_26_27.pdf`, pages 1–4 : compréhension du candidat, adaptation linguistique, mémoire, orientation prudente, respect des données officielles, et non-substitution à une décision académique.

Le livrable n'est **pas** un entraînement/fine-tuning et ne prétend pas que le modèle est déjà évalué. Les véritables comparaisons de plusieurs modèles, l'étude détaillée de la qualité tunisienne et le réglage du prompt relèvent ensuite des tâches d'évaluation SA-33/34/38.

## 2. Jeu de données

`evaluation/cases.jsonl` : **72 questions / 60 scénarios indépendants**.

| Catégorie | Questions | Objectif |
|---|---:|---|
| welcome | 8 | Conversation d'accueil |
| intent | 10 | Détection de l'intention |
| profiling | 8 | Recueil d'intérêts et contraintes |
| orientation | 8 | Critères et explications sans imposer une décision |
| reliability | 8 | Non-invention de tarifs, dates, critères officiels, sources |
| boundaries | 6 | Non-simulation d'admission, QCM, e-mails ou rendez-vous |
| memory | 24 | 12 scénarios de 2 tours avec rappel vérifiable |
| **Total** | **72** | |

Répartition linguistique équilibrée : **18 français / 18 tunisien arabe / 18 Arabizi / 18 mixte**. Chaque ligne comprend `case_id`, `scenario_id`, `turn`, `language`, `category`, `prompt`, `expected_behavior`, `checks`, `review_criteria`.

Les exemples de profils sont **fictifs** : ne saisir aucune information réelle d'un étudiant dans ce jeu de tests. Les tarifs officiels et les conditions d'accès ne sont pas inventés. Pour les questions factuelles, la grille vérifie si le modèle admet l'absence de source vérifiée, plutôt que d'imposer une fausse réponse.

## 3. Installation / lancement Windows

**Prérequis** : `smoke_chat.ps1` a déjà renvoyé `PASS` avec Qwen3.5, Docker/API sont démarrés sur `127.0.0.1:8001`. Aucun rebuild Docker, aucune migration, aucune nouvelle bibliothèque Python : le runner n'utilise que la bibliothèque standard Python.

Dans `D:\SmartCampus_AI_Backend_v1` :

```powershell
python evaluation/run_eval.py --validate

# Petit échantillon réel : 8 scénarios (dont 3 scénarios mémoire complets)
.\scripts\evaluate_llm.ps1

# Filtre utile pour travailler uniquement la mémoire
.\scripts\evaluate_llm.ps1 -All -Category memory

# Campagne complète : 72 requêtes réelles sur 60 sessions
.\scripts\evaluate_llm.ps1 -All
```

La première commande valide le fichier sans appeler le LLM. Les autres utilisent la même route `/api/v1/visitor/sessions/{id}/chat` que le test SA-36/37. Le benchmark crée une nouvelle session par scénario, exécute les tours dans l'ordre puis **supprime la session même en cas d'échec**. Aucune connexion administrateur n'est nécessaire ; aucun jeton visiteur n'est écrit dans les rapports. Si le DELETE échoue, le rapport indique le scénario et le risque de session orpheline.

Pour une campagne ciblée, `python evaluation/run_eval.py --all --language arabizi --max-scenarios 5` exécute cinq scénarios Arabizi **complets**. Le paramètre `--timeout 360` peut être ajusté, sans modifier le délai configuré côté API. Lancer un petit test avant la campagne complète, qui peut prendre un certain temps car chaque question entraîne une génération réelle.

## 4. Résultats, vérification humaine et métriques

Chaque exécution crée un dossier horodaté `evaluation/results/<UTC>/` :

- `results.jsonl` : une ligne de résultat par question (réponse réelle, modèle déclaré par l'API, temps, état, attentes) ;
- `summary.json` : nombre de cas, répartition, empreinte SHA-256 du corpus, statuts automatiques, temps médian, p95 approximatif (nearest-rank), alertes de nettoyage ;
- `manual_review.csv` : tableau à compléter à la main (encodage compatible Excel Windows).

**Automatique ≠ jugement de qualité.** Les 12 dernières questions des scénarios mémoire ont des ancrages textuels (`must_contain_any`) : le programme signale PASS/FAIL uniquement selon les mots attendus. Les questions ouvertes restent `REVIEW`, jamais automatiquement `PASS`. Un `PASS` lexical ne prouve ni exactitude factuelle ni bon dialecte. Les requêtes non abouties sont `ERROR`, et les tours dépendants sont `SKIPPED` : ne pas les inclure dans les métriques de qualité.

### Barème d'examen humain (0 à 3, par dimension)

| Score | Interprétation |
|---|---|
| 0 | Réponse erronée, inventée, dangereuse ou dans une langue inadaptée |
| 1 | Compréhension ou qualité faible, plusieurs défauts importants |
| 2 | Réponse utile avec quelques imprécisions ou maladresses |
| 3 | Bonne compréhension, naturel, prudence et qualité satisfaisante |

Dans `manual_review.csv`, remplir les cinq colonnes **uniquement quand elles sont pertinentes** : `language_score_0_to_3`, `intent_score_0_to_3`, `grounding_score_0_to_3`, `memory_score_0_to_3`, `safety_score_0_to_3`. Laisser vide lorsqu'on ne peut pas juger (ne pas inventer une note). La **fidélité du rappel** doit être évaluée en relisant les deux tours de mémoire ; la **prudence factuelle** doit être évaluée par rapport au catalogue officiel effectivement publié, s'il existe.

Puis calculer la synthèse des évaluations humaines :

```powershell
python evaluation/score_reviews.py "evaluation/results/<UTC>/manual_review.csv"
```

Le script indique la moyenne sur 0–3 **avec le nombre de réponses réellement évaluées** pour chaque dimension et langue. Les champs vides restent non notés.

## 5. Comparaison de modèles (futur SA-33/34)

Pour comparer `qwen3.5:4b` avec un autre modèle : lancer exactement le **même fichier JSONL** et relever le même `dataset_sha256`; utiliser la même configuration de température (0,2), de limite de sortie, de taille de contexte et le même catalogue publié. Ne jamais mélanger scores lexicaux et scores humains ni afficher un taux global trompeur si beaucoup de cas sont `REVIEW`. Exécuter les modèles séquentiellement sur la même machine et documenter version/quantification/GPU, latence, erreurs et qualité par langue.

L'évaluation de l'Arabizi doit tenir compte de ses graphies variables (ex : `3` pour ع, `7` pour ح) ; la présence d'un seul mot-clé ne suffit pas à mesurer la compréhension dialectale.

## 6. Données, limites et acceptation SA-32

- À remettre : corpus JSONL, script de validation/exécution, générateur de rapport et grille de relecture.
- À démontrer : `--validate` sans erreur, puis une campagne `--smoke` avec réponses réelles et rapports écrits sur Windows.
- Les sessions de benchmark utilisent PostgreSQL temporairement, mais sont supprimées à la fin de chaque scénario. Les journaux et exports doivent rester privés : `.gitignore` exclut `evaluation/results/`.
- **Ne pas présenter de moyennes de qualité avant la notation humaine**. Ne pas affirmer qu'une admission, un tarif ou un programme est officiel sans source institutionnelle vérifiée.
- Le backend n'effectue toujours pas de STT/TTS, de RAG documentaire complet ou de fine-tuning. Les tests évaluent le comportement actuel, pas des fonctions futures.
