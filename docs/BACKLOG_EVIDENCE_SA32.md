# Task SA-32 — Evidence pack

**Backlog task:** Préparer les jeux de questions pour évaluer les LLM.

**Implemented / reproducible**

- Structured, synthetic multilingual benchmark: `evaluation/cases.jsonl` (72 cases, 60 scenarios, 18 cases per language).
- Tests for data integrity, isolated visitor session lifecycle, API request contract, reporting, and error recovery: `evaluation/tests/test_eval_runner.py`.
- Real backend evaluator: `evaluation/run_eval.py`. Sends to `/api/v1/visitor/sessions/{id}/chat`; no invented replies in production runs.
- Human grading exporter: `manual_review.csv` from evaluator; review aggregation `evaluation/score_reviews.py`.
- Windows interface: `scripts/evaluate_llm.ps1`.
- Evaluation and scoring instructions: `docs/SA32_EVALUATION.md`.

**Local code checks performed:** `python evaluation/run_eval.py --validate`, `python -m unittest discover -s evaluation/tests -v` (13 passed), existing `python -m pytest -q` (71 passed). API mock-server test proves HTTP request structure but is *not* a real model-quality result.

**Real model run:** Pending on Windows, run `./scripts/evaluate_llm.ps1`; results are created in `evaluation/results/` and are not included in this package. Human scoring is mandatory before any claims about Tunisian/Arabizi proficiency or hallucination rate.

**Backlog boundary:** SA-32 prepares questions, protocol, and runnable evaluation harness. SA-33/SA-34 comparisons and SA-38 conversation evaluation remain separate follow-up tasks.
