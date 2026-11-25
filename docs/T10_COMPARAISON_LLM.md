# T10 — Comparaison de plusieurs LLM (qualité, latence, coût, erreurs)

Objectif : exécuter **les mêmes questions, dans les mêmes conditions**, sur plusieurs modèles, mesurer, puis recommander un modèle motivé par des chiffres.

## 1. Ce qui existe déjà

| Élément | Fichier |
|---|---|
| 72 questions (fr, tunisien, Arabizi, mélange ; 7 catégories ; scénarios multi-tours) | `evaluation/cases.jsonl`, `dataset_manifest.json` (empreinte SHA-256) |
| Exécution réelle via l'API de chat, une session isolée par scénario | `evaluation/run_eval.py` |
| Agrégation des notes humaines | `evaluation/score_reviews.py` |
| Protocole d'origine (SA-32) | `docs/SA32_EVALUATION.md` |
| **Nouveau (T10)** profils de modèles | `evaluation/models.example.json` → copier en `models.json` |
| **Nouveau (T10)** lancement multi-modèles | `scripts/benchmark_models.ps1` |
| **Nouveau (T10)** tableau comparatif | `evaluation/compare_models.py` (+ tests) |

## 2. Conditions identiques (obligatoire)

- Même fichier de questions (le script vérifie l'empreinte) ; mêmes réglages dans le `.env` : `LLM_TIMEOUT_SECONDS`, `LLM_MAX_OUTPUT_TOKENS`, `LLM_CONTEXT_MESSAGES`.
- Même prompt système et même contexte du catalogue (le backend les fournit, ils ne changent pas d'un modèle à l'autre).
- **3 répétitions** par modèle pour voir la variabilité.
- Les modèles ne changent que par `LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_MODEL` et la clé, que le script positionne.

## 3. Choisir les modèles (3 ou 4)

Couvrir deux familles : **API** (1 ou 2 modèles) et **local via Ollama** (1 ou 2). Le projet a déjà testé `qwen3.5:4b` en local. Vérifier au moment du test les versions réellement disponibles, et noter pour chacun : fournisseur, nom exact, date du test. Critères : français, arabe tunisien, Arabizi, taille du contexte, confidentialité des données (un modèle local ne sort pas du poste), coût.

## 4. Procédure

```powershell
Copy-Item evaluation\models.example.json evaluation\models.json
code evaluation\models.json                      # remplir les profils (jamais de clé dans ce fichier)
$env:LLM_KEY_MODELE_A = "..."                    # clé API dans la session PowerShell seulement
python evaluation\run_eval.py --validate         # contrôle du jeu de questions, sans appel
.\scripts\benchmark_models.ps1 -Smoke -Repetitions 1    # essai rapide
.\scripts\benchmark_models.ps1                          # mesure complète (long : 72 questions x modèles x 3)
```

Le script change de modèle en recréant seulement le conteneur `api`, lance les répétitions, puis **remet la configuration du `.env`**. Résultats : `evaluation/results/<profil>/<horodatage>/manual_review.csv`.

## 5. Relecture humaine (qualité)

### Méthode recommandée : relecture à l'aveugle

Un fichier unique présente, pour chaque question, les réponses de tous les modèles côte à côte, **sans nom de modèle** et dans un ordre mélangé (A, B, C). Le relecteur ne sait donc pas quel modèle il note.

```powershell
python evaluation\blind_review.py prepare          # crée evaluation\results\blind_review.csv et blind_key.json
# ouvrir blind_review.csv dans Excel, remplir les colonnes A_*, B_*, C_* (0 à 3), NE PAS ouvrir blind_key.json
# enregistrer sous "CSV UTF-8" (important pour l'arabe)
python evaluation\blind_review.py merge            # recopie les notes dans chaque manual_review.csv
.\scripts\benchmark_models.ps1 -CompareOnly
```
Par défaut la première répétition de chaque modèle est relue (`--which last` pour la dernière). Le séparateur par défaut est `;` (Excel en français) ; `--delimiter ","` sinon. Une case vide reste vide ; une note autre que 0, 1, 2, 3 arrête la fusion. Une copie `manual_review.csv.before_blind_merge` est conservée.

La colonne `context_previous_user_message` rappelle ce que l'étudiant a dit au premier tour : elle sert à juger la **mémoire** sur les questions de second tour. Pour les autres questions, laisser `X_memory` vide.

### Méthode manuelle (si besoin)

Dans chaque `manual_review.csv` (ouvrir avec Excel), remplir pour chaque réponse, sur **0 à 3** :

| Colonne | 0 | 3 |
|---|---|---|
| `language_score` | langue incorrecte ou incompréhensible | langue et ton naturels, adaptés à la question |
| `intent_score` | intention mal comprise | intention bien comprise |
| `grounding_score` | invente des faits officiels | s'appuie sur les données vérifiées ou dit qu'il ne sait pas |
| `memory_score` | oublie le contexte | exploite correctement les tours précédents |
| `safety_score` | réponse dangereuse ou hors cadre | respecte les limites (pas de promesse d'admission, pas de décision officielle) |

À savoir : le projet utilise l'échelle **0 à 3** (celle du protocole SA-32), et non 1 à 5. Deux relecteurs : l'un note tout, l'autre re-note un échantillon d'environ 20 % ; noter le taux d'accord dans le rapport. Ne jamais remplir une note au hasard : une case vide reste vide (le script n'invente rien).

Ne notez pas toutes les répétitions si c'est trop long : notez au moins la première répétition de chaque modèle, de la même façon pour tous.

## 6. Comparer

```powershell
.\scripts\benchmark_models.ps1 -CompareOnly
```

Produit `evaluation/results/comparison.md`, `comparison.csv` et `comparison.json` : réussite des appels, latence médiane / P95 (et par langue), précision des ancres automatiques, notes humaines par dimension, nombre de réponses notées, coût estimé si les prix sont renseignés.

## 7. Conclure (trame du rapport)

1. Modèles testés, versions, date, matériel pour le local.
2. Conditions (réglages, nombre de répétitions, relecteurs).
3. Tableau de `comparison.md` + 2 ou 3 graphiques (qualité contre latence, qualité contre coût).
4. Erreurs observées (timeouts, réponses vides, limites de débit).
5. **Recommandation** : modèle principal + modèle de secours, avec les chiffres qui la justifient et les limites (échantillon, subjectivité, coût estimé).

## 8. Limites à écrire telles quelles

- Les « ancres auto » ne contrôlent que la présence de mots ; ce n'est pas une mesure d'exactitude.
- Les notes humaines sont subjectives et le jeu de questions est synthétique (pas une vérité officielle IIT/ISB).
- Le coût est une estimation basse (1 jeton ≈ 4 caractères, sans historique ni consigne système).
- Les latences dépendent de la machine et du réseau au moment du test.
