import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from evaluation.run_eval import BenchmarkError, DEFAULT_DATASET, load_cases, parse_args, selected_groups
from evaluation.triage_results import latest_run, load_run, make_report


class TargetedEvaluationTests(unittest.TestCase):
    def test_scenarios_preserve_both_turns_and_original_order(self):
        groups = selected_groups(load_cases(DEFAULT_DATASET), scenario_ids=["MEM-10", "MEM-06"])
        self.assertEqual(list(groups), ["MEM-06", "MEM-10"])
        self.assertEqual([len(turns) for turns in groups.values()], [2, 2])

    def test_unknown_scenario_rejected(self):
        with self.assertRaisesRegex(BenchmarkError, "Unknown scenario"):
            selected_groups(load_cases(DEFAULT_DATASET), scenario_ids=["MEM-999"])

    def test_cli_accepts_repeated_scenarios(self):
        args = parse_args(["--all", "--scenario", "MEM-06", "--scenario", "MEM-10"])
        self.assertEqual(args.scenario, ["MEM-06", "MEM-10"])

    def test_smoke_and_targeted_filter_not_accepted(self):
        with self.assertRaises(SystemExit) as exc:
            parse_args(["--smoke", "--scenario", "MEM-06"])
        self.assertEqual(exc.exception.code, 2)


class TriageTests(unittest.TestCase):
    def test_inspect_full_run_without_mutating_evaluation_results(self):
        results = [
            {"case_id": "MEM-06-T2", "turn": 2, "category": "memory", "language": "arabizi",
             "auto_status": "FAIL", "prompt": "Chnowa?", "response": "analyste de donnees",
             "expected_behavior": "Remember job", "auto_checks_failed": ["must_contain_any"], "reviewer_notes": ""},
            {"case_id": "MEM-10-T1", "turn": 1, "category": "memory", "language": "arabizi",
             "auto_status": "ERROR", "prompt": "Hi", "response": "", "expected_behavior": "Reply",
             "auto_checks_failed": [], "reviewer_notes": "Backend returned HTTP 502 (POST)"},
            {"case_id": "MEM-10-T2", "turn": 2, "category": "memory", "language": "arabizi",
             "auto_status": "SKIPPED", "prompt": "Remember?", "response": "", "expected_behavior": "Recall",
             "auto_checks_failed": [], "reviewer_notes": "Prior turn failed"},
        ]
        summary = {"dataset_sha256": "abc", "cleanup_warnings": []}
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root) / "test_run"
            folder.mkdir()
            raw = "".join(json.dumps(row) + "\n" for row in results)
            (folder / "results.jsonl").write_text(raw, encoding="utf-8")
            (folder / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
            self.assertEqual(latest_run(Path(root)), folder)
            rows, info = load_run(folder)
            report = make_report(rows, info, folder)
            self.assertIn("analyste de donnees", report)
            self.assertIn("HTTP 502", report)
            self.assertIn("skipped", report.lower())
            self.assertIn("MEM-06 --scenario MEM-10", report)
            self.assertEqual((folder / "results.jsonl").read_text(encoding="utf-8"), raw)

    def test_missing_results_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "results.jsonl"):
                load_run(Path(root))


if __name__ == "__main__":
    unittest.main()
