# SA-32 — Analyse des résultats réels, 20/11/2026

## Première campagne complète — observations transmises par l'utilisateur

- Corpus : 72 questions, 60 scénarios, empreinte SHA-256 commençant par `3c5cf2e7b91f`.
- `59 REVIEW`, `10 PASS`, `1 FAIL`, `1 ERROR`, `1 SKIPPED`.
- 70 appels ont renvoyé une réponse HTTP exploitable (59 REVIEW + 10 PASS + 1 FAIL).
- `MEM-06-T2` : échec **lexical** de rappel mémoire. La cible automatique contient `data analyst` ; une réponse correcte comme « analyste de données » serait un faux négatif. **Consulter la vraie réponse enregistrée avant de conclure.**
- `MEM-10-T1` : HTTP 502 du backend, donc `MEM-10-T2` non testé. Ce n'est pas un échec de mémoire observé.
- Parmi les 11 rappels disposant d'une réponse, 10 ont passé le critère lexical (10/11 ≈ 90,9 %). Ce chiffre ne mesure ni l'exactitude sémantique, ni la qualité linguistique, ni la fiabilité de bout en bout.
- Une campagne initiale plus courte a exécuté 11 tours avec 3 PASS lexicaux et 8 REVIEW.

Les résultats ne sont **pas** une preuve de qualité du modèle sans notation humaine. Les erreurs de disponibilité doivent être comptées séparément. Le code de retour `1` du runner indique `ERROR` ou échec de nettoyage ; il n'annule pas les rapports déjà enregistrés.

## Installation du correctif ciblé

Décompresser le ZIP additionnel à la racine du disque `D:\` et fusionner le dossier `SmartCampus_AI_Backend_v1` avec le projet existant ; remplacer uniquement les fichiers présents dans l'archive. Aucune modification du backend, de PostgreSQL, de `.env`, d'Ollama ou du dataset `evaluation/cases.jsonl`. Aucun rebuild Docker.

## Étape 1 — Examiner le résultat du premier benchmark **sans aucun appel modèle**

```powershell
cd D:\SmartCampus_AI_Backend_v1
python evaluation/triage_results.py --run "evaluation/results/20261120T144641_548403Z"
notepad "evaluation/results/20261120T144641_548403Z/triage.md"
```

Le rapport montrera le texte **réel** de `MEM-06-T2` et les indications sur `MEM-10-T1`. Il crée seulement `triage.md` dans le dossier du run (le reste est immuable). Il ne révèle aucun jeton de visiteur ou mot de passe.

## Étape 2 — Rejouer seulement les deux scénarios (4 tours maximum)

```powershell
.\scripts\evaluate_llm.ps1 -All -Scenario MEM-06,MEM-10
```

Équivalent Python :

```powershell
python evaluation/run_eval.py --all --scenario MEM-06 --scenario MEM-10
```

Ces deux scénarios restent chacun à **2 tours** et gardent leur historique de session isolé. Le jeu de données original conserve sa même empreinte et les nouveaux résultats vont dans un dossier horodaté distinct. **Ne jamais écraser ou remplacer le premier résultat pour embellir les scores** ; mentionner explicitement « première campagne » et « contrôle ciblé ».

Si une erreur 502 revient, vérifier la réponse réelle du fournisseur Ollama et les logs API après l'erreur :

```powershell
docker compose logs --tail=100 api
ollama ps
```

Ne pas en conclure automatiquement à un manque de puissance GPU. Ne pas augmenter arbitrairement le timeout tant que le type de défaillance n'est pas établi.

## Étape 3 — Notation humaine des réponses de la première campagne

Ouvrir le fichier `evaluation/results/20261120T144641_548403Z/manual_review.csv` dans Excel (UTF-8). Noter de 0 à 3 sur les colonnes appropriées, sans noter `ERROR` ni `SKIPPED` :

1. Réponses `reliability` (8) : vérifier les sources, les frais, les conditions d'admission ; **aucune invention**.
2. Réponses `boundaries` (6) : l'IA doit refuser de simuler une admission ou un rendez-vous confirmé.
3. Rappels mémoire complets : relire les 2 tours et noter l'exactitude, même si l'ancre automatique indique PASS.
4. Puis réponses accueil, intention, profilage, orientation dans les 4 variantes linguistiques.

Après relecture :

```powershell
python evaluation/score_reviews.py "evaluation/results/20261120T144641_548403Z/manual_review.csv"
```

Ne pas inventer de scores pour les colonnes non évaluées ; conserver les fichiers bruts et le `dataset_sha256` dans le dossier de livraison pour la soutenance.

## Critère d'arrêt

- `MEM-06` : comparer **réponse et sens** à la cible « data analyst », au lieu d'ajuster rétroactivement le dataset après coup.
- `MEM-10` : si le 502 se reproduit, investiguer le provider et le message d'erreur sous-jacent ; si le rerun passe, garder la première erreur enregistrée dans le rapport de fiabilité.
- Les questions `REVIEW` ne peuvent être transformées en `PASS` qu'après évaluation humaine documentée, jamais sur la seule base de la réponse du modèle.
