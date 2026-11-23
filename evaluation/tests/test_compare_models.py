import csv
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.compare_models import compare, discover, p95, summarize_profile, to_markdown
from evaluation.run_eval import CSV_COLUMNS


def write_run(root: Path, profile: str, stamp: str, rows: list[dict], sha: str = "abc") -> Path:
    run = root / profile / stamp
    run.mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps({"dataset_sha256": sha}), encoding="utf-8")
    with (run / "manual_review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            base = {c: "" for c in CSV_COLUMNS}
            base.update(
                {
                    "api_status": "OK",
                    "auto_status": "NOT_CHECKED",
                    "language": "fr",
                    "model": "m1",
                    "prompt": "x" * 40,
                    "response": "y" * 80,
                    "latency_seconds": "2.0",
                }
            )
            base.update(row)
            writer.writerow(base)
    return run


class CompareModelsTest(unittest.TestCase):
    def test_p95_nearest_rank(self):
        self.assertEqual(p95([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]), 10)
        self.assertEqual(p95([5.0]), 5.0)
        self.assertIsNone(p95([]))

    def test_metrics_errors_and_human_scores(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_run(
                root,
                "a",
                "1",
                [
                    {
                        "latency_seconds": "1.0",
                        "auto_status": "PASS",
                        "language_score_0_to_3": "3",
                        "intent_score_0_to_3": "2",
                    },
                    {"latency_seconds": "3.0", "auto_status": "FAIL", "language_score_0_to_3": "1"},
                    {"api_status": "ERROR", "auto_status": "ERROR", "latency_seconds": ""},
                    {"api_status": "SKIPPED", "auto_status": "SKIPPED", "latency_seconds": ""},
                ],
            )
            cfg = {"price_per_million_input_usd": 1.0, "price_per_million_output_usd": 2.0}
            r = summarize_profile("a", discover(root)["a"], cfg)
            self.assertEqual((r["calls"], r["ok"], r["errors"]), (3, 2, 1))  # SKIPPED is not a call
            self.assertAlmostEqual(r["ok_rate"], 2 / 3, places=3)
            self.assertEqual(r["latency_median_s"], 2.0)
            self.assertEqual(r["anchor_accuracy"], 0.5)
            self.assertEqual(r["human_means"]["language"], 2.0)
            self.assertEqual(r["human_means"]["intent"], 2.0)
            self.assertIsNone(r["human_means"]["safety"])  # never invented
            self.assertEqual(r["human_scored_answers"], 2)
            # 2 OK answers: 80 prompt chars, 160 answer chars -> 20 and 40 tokens
            self.assertAlmostEqual(r["estimated_cost_usd"], (20 * 1.0 + 40 * 2.0) / 1e6, places=4)

    def test_missing_price_gives_no_cost(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_run(Path(tmp), "a", "1", [{}])
            r = summarize_profile(
                "a",
                discover(Path(tmp))["a"],
                {"price_per_million_input_usd": None, "price_per_million_output_usd": None},
            )
            self.assertIsNone(r["estimated_cost_usd"])

    def test_invalid_human_score_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_run(Path(tmp), "a", "1", [{"language_score_0_to_3": "5"}])
            with self.assertRaises(ValueError):
                summarize_profile("a", discover(Path(tmp))["a"], None)

    def test_different_datasets_invalidate_comparison_and_warnings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_run(root, "a", "1", [{}], sha="one")
            write_run(root, "b", "1", [{}], sha="two")
            result = compare(root, None)
            text = " ".join(result["warnings"])
            self.assertIn("INVALIDE", text)
            self.assertIn("aucune note humaine", text)
            self.assertIn("répétition", text)
            md = to_markdown(result)
            self.assertIn("| a |", md)
            self.assertIn("n/a", md)

    def test_unscored_runs_are_not_given_a_quality_number(self):
        with tempfile.TemporaryDirectory() as tmp:
            write_run(Path(tmp), "a", "1", [{}])
            r = compare(Path(tmp), None)["profiles"][0]
            self.assertIsNone(r["human_overall_mean_0_to_3"])


if __name__ == "__main__":
    unittest.main()
