import csv
import tempfile
import unittest
from pathlib import Path

from evaluation import blind_review
from evaluation.compare_models import DIMENSIONS

COLS = (
    [
        "case_id",
        "scenario_id",
        "turn",
        "language",
        "category",
        "model",
        "prompt",
        "response",
        "expected_behavior",
        "latency_seconds",
        "api_status",
        "auto_status",
        "auto_checks_failed",
    ]
    + [f"{d}_score_0_to_3" for d in DIMENSIONS]
    + ["reviewer_notes"]
)


def make_run(root: Path, profile: str, tag: str):
    run = root / profile / "20260101T000000_000000Z"
    run.mkdir(parents=True)
    rows = [
        {
            "case_id": "C1",
            "scenario_id": "C1",
            "turn": "1",
            "language": "fr",
            "category": "welcome",
            "prompt": "Bonjour",
            "response": f"{tag}-r1",
            "expected_behavior": "x",
        },
        {
            "case_id": "M1-T1",
            "scenario_id": "M1",
            "turn": "1",
            "language": "derja",
            "category": "memory",
            "prompt": "نحب الرياضيات",
            "response": f"{tag}-m1",
            "expected_behavior": "x",
        },
        {
            "case_id": "M1-T2",
            "scenario_id": "M1",
            "turn": "2",
            "language": "derja",
            "category": "memory",
            "prompt": "شنية المادة؟",
            "response": f"{tag}-m2",
            "expected_behavior": "x",
        },
    ]
    with (run / "manual_review.csv").open("w", encoding="utf-8-sig", newline="") as s:
        w = csv.DictWriter(s, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({**{c: "" for c in COLS}, **r})
    return run


class BlindReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runs = {n: make_run(self.root, n, n) for n in ("alpha", "beta", "gamma")}

    def tearDown(self):
        self.tmp.cleanup()

    def _fill(self, path: Path, value_for):
        rows = list(csv.DictReader(path.open(encoding="utf-8-sig"), delimiter=";"))
        key = blind_review.json.loads((self.root / "blind_key.json").read_text(encoding="utf-8"))[
            "labels"
        ]
        for row in rows:
            for label, profile in key[row["case_id"]].items():
                for dim in DIMENSIONS:
                    row[f"{label}_{dim}"] = value_for(profile, dim)
        with path.open("w", encoding="utf-8-sig", newline="") as s:
            w = csv.DictWriter(s, fieldnames=list(rows[0]), delimiter=";")
            w.writeheader()
            w.writerows(rows)

    def test_prepare_hides_model_names_and_gives_context(self):
        csv_path, key_path = blind_review.prepare(self.root, None, "first", 1, ";")
        text = csv_path.read_text(encoding="utf-8-sig")
        for name in ("alpha", "beta", "gamma"):
            self.assertNotIn(f"{name}\n", text.split("\n", 1)[0])
        rows = list(csv.DictReader(text.splitlines(), delimiter=";"))
        self.assertEqual(len(rows), 3)
        t2 = next(r for r in rows if r["case_id"] == "M1-T2")
        self.assertEqual(t2["context_previous_user_message"], "نحب الرياضيات")
        self.assertEqual(
            sorted(r.split("-")[0] for r in (t2["response_A"], t2["response_B"], t2["response_C"])),
            ["alpha", "beta", "gamma"],
        )

    def test_same_seed_is_reproducible(self):
        a, _ = blind_review.prepare(self.root, None, "first", 7, ";")
        first = a.read_text(encoding="utf-8-sig")
        b, _ = blind_review.prepare(self.root, None, "first", 7, ";")
        self.assertEqual(first, b.read_text(encoding="utf-8-sig"))

    def test_merge_copies_scores_to_the_right_model_and_keeps_empty(self):
        csv_path, _ = blind_review.prepare(self.root, None, "first", 3, ";")
        self._fill(csv_path, lambda profile, dim: {"alpha": "3", "beta": "1", "gamma": ""}[profile])
        written = blind_review.merge(self.root, None)
        self.assertEqual(written["alpha"], 15)
        self.assertEqual(written["gamma"], 0)
        rows = list(
            csv.DictReader((self.runs["beta"] / "manual_review.csv").open(encoding="utf-8-sig"))
        )
        self.assertTrue(all(r["language_score_0_to_3"] == "1" for r in rows))
        rows = list(
            csv.DictReader((self.runs["gamma"] / "manual_review.csv").open(encoding="utf-8-sig"))
        )
        self.assertTrue(all(r["language_score_0_to_3"] == "" for r in rows))
        self.assertTrue(
            (self.runs["alpha"] / ("manual_review.csv" + blind_review.BACKUP_SUFFIX)).exists()
        )

    def test_invalid_score_stops_the_merge(self):
        csv_path, _ = blind_review.prepare(self.root, None, "first", 3, ";")
        self._fill(csv_path, lambda profile, dim: "5")
        with self.assertRaises(SystemExit):
            blind_review.merge(self.root, None)

    def test_comma_separated_file_is_accepted(self):
        csv_path, _ = blind_review.prepare(self.root, None, "first", 3, ",")
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8-sig")))
        self.assertEqual(len(rows), 3)
        self.assertEqual(blind_review.merge(self.root, None)["alpha"], 0)


if __name__ == "__main__":
    unittest.main()
