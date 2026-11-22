# T8 — Tests des API (tarifs, modalités de paiement, conditions d'admission)

## Lancer
```powershell
python -m pytest -q                                   # toute la suite (SQLite), ~200 tests
python -m pytest tests/test_t8_catalogue_api.py -v    # uniquement T8
.\scripts\smoke_t8.ps1                                # test de bout en bout sur la vraie PostgreSQL (demande le login admin)
```
`smoke_t8.ps1` crée un seul programme fictif `CHECK-T8-…` et l'archive à la fin (un programme archivé n'expose rien).

## Matrice de couverture
| Exigence | Où c'est testé |
|---|---|
| Création / lecture / modification / suppression des 3 ressources | `test_payment_and_validity.py`, `test_academic_details.py`, `test_t8_catalogue_api.py::test_full_workflow…` |
| Statut de publication (PUBLISHED / DRAFT / ARCHIVED) | `test_payment_and_validity.py`, `test_full_workflow…` |
| Période de validité (expirée, future, illimitée, bornes incohérentes, datetime sans fuseau) | `test_payment_and_validity.py`, `test_validity_window_must_be_ordered…` |
| Visible au public seulement si : formation publiée + source HTTPS + vérifiée + publiée + valide | `test_full_workflow…`, `test_draft_programme_exposes_nothing…`, `test_archiving_the_programme…` |
| Modifier le contenu retire la vérification ; changer le statut ne la retire pas | `test_full_workflow…` |
| Droits par rôle (anonyme 401, DIRECTION lecture seule 403, INTERVIEW_MANAGER 403, ADMIN tout) | `test_anonymous_and_invalid_tokens…`, `test_direction_reads…`, `test_interview_manager…` |
| Isolation par établissement (IIT ne touche pas ISB → 404) | `test_academic_staff_cannot_touch_another_institution` |
| Erreurs : 404 (programme inconnu), 422 (UUID invalide, champ inconnu, montant invalide, mode de paiement incohérent), 409 (doublon) | `test_unknown_program…`, `test_unknown_fields…`, `test_amount_validation`, `test_duplicate_tuition…` |
| Pagination (limit/offset, pas de doublon ni de trou, bornes 422) | `test_public_pagination` |
| Vue complète d'un programme pour le frontend / chatbot | `test_candidate_view_of_a_complete_programme` |

## Hors périmètre (volontairement)
- Les tests tournent sur SQLite pour la rapidité ; les contraintes propres à PostgreSQL sont couvertes par `smoke_t8.ps1`
  et par `TEST_DATABASE_URL` (base **jetable** uniquement, jamais la base réelle : les tests suppriment des lignes).
- Aucune donnée officielle IIT/ISB n'est utilisée dans les tests.
