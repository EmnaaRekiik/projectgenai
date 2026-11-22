import csv
import json
import tempfile
import unittest
from pathlib import Path

from evaluation.run_eval import (
    DEFAULT_DATASET,
    BenchmarkError,
    HttpChatTransport,
    build_summary,
    check_response,
    load_cases,
    run_benchmark,
    selected_groups,
    write_report,
)
from evaluation.score_reviews import aggregate, grade


class FakeChatTransport:
    def __init__(self, fail_on_turn=0):
        self.created = []
        self.deleted = []
        self.responses = []
        self.current_turn = 0
        self.fail_on_turn = fail_on_turn

    def create_session(self):
        session = {"id": str(len(self.created) + 1), "token": "SECRET_NOT_FOR_REPORTS"}
        self.created.append(session)
        self.current_turn = 0
        return session

    def chat(self, session_id, token, prompt):
        self.current_turn += 1
        if self.current_turn == self.fail_on_turn:
            raise BenchmarkError("Backend returned HTTP 502 (POST)")
        return {
            "model": "fake-in-tests-only",
            "user_message": {"sequence": self.current_turn * 2 - 1},
            "assistant_message": {
                "sequence": self.current_turn * 2,
                "content": "La robotique est votre intérêt.",
            },
        }

    def delete_session(self, session_id, token):
        self.deleted.append(session_id)


class DataTests(unittest.TestCase):
    def test_dataset_size_and_scenario_count(self):
        rows = load_cases(DEFAULT_DATASET)
        self.assertEqual(len(rows), 72)
        self.assertEqual(len({r["scenario_id"] for r in rows}), 60)

    def test_balanced_languages(self):
        rows = load_cases(DEFAULT_DATASET)
        for language in ("fr", "derja", "arabizi", "mixed"):
            self.assertEqual(sum(r["language"] == language for r in rows), 18)

    def test_memory_pairs_and_anchors(self):
        rows = load_cases(DEFAULT_DATASET)
        mem = [r for r in rows if r["category"] == "memory"]
        self.assertEqual(len(mem), 24)
        self.assertEqual(sum(bool(r["checks"]) for r in mem), 12)

    def test_duplicate_cases_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = load_cases(DEFAULT_DATASET)[0]
            path = Path(tmp) / "cases.jsonl"
            path.write_text("\n".join([json.dumps(first), json.dumps(first)]), encoding="utf-8")
            with self.assertRaisesRegex(BenchmarkError, "Duplicate"):
                load_cases(path)

    def test_scenarios_have_full_turns_after_filtering(self):
        rows = load_cases(DEFAULT_DATASET)
        groups = selected_groups(rows, category="memory", max_scenarios=3)
        self.assertEqual(len(groups), 3)
        self.assertTrue(all(len(v) == 2 for v in groups.values()))

    def test_lexical_anchor_matching_is_accent_insensitive(self):
        self.assertEqual(
            check_response("J'aime la CYBERSÉCURITÉ", {"must_contain_any": ["cybersecurite"]})[0],
            "PASS",
        )
        self.assertEqual(
            check_response("Je préfère le design", {"must_contain_any": ["robotique"]})[0], "FAIL"
        )
        self.assertEqual(check_response("bonjour", {})[0], "REVIEW")

    def test_reject_remote_api_host_by_default(self):
        with self.assertRaisesRegex(BenchmarkError, "localhost"):
            HttpChatTransport("https://example.org/api/v1")


class ExecutionTests(unittest.TestCase):
    def test_two_turn_session_is_deleted_and_token_not_reported(self):
        rows = load_cases(DEFAULT_DATASET)
        group = selected_groups(rows, category="memory", max_scenarios=1)
        transport = FakeChatTransport()
        results, warnings = run_benchmark(group, transport, progress=False)
        self.assertEqual(len(transport.created), 1)
        self.assertEqual(transport.deleted, ["1"])
        self.assertEqual([r["auto_status"] for r in results], ["REVIEW", "PASS"])
        self.assertFalse(warnings)
        self.assertNotIn("SECRET_NOT_FOR_REPORTS", json.dumps(results))
        summary = build_summary(results, warnings, dataset_sha="abc", scenario_count=1)
        self.assertEqual(summary["automatic_anchor_accuracy"], 1.0)

    def test_failed_turn_skips_later_turn_and_deletes(self):
        rows = load_cases(DEFAULT_DATASET)
        group = selected_groups(rows, category="memory", max_scenarios=1)
        transport = FakeChatTransport(fail_on_turn=1)
        results, _ = run_benchmark(group, transport, progress=False)
        self.assertEqual([r["auto_status"] for r in results], ["ERROR", "SKIPPED"])
        self.assertEqual(transport.deleted, ["1"])

    def test_report_includes_reviewable_csv(self):
        rows = load_cases(DEFAULT_DATASET)
        group = selected_groups(rows, category="memory", max_scenarios=1)
        results, warnings = run_benchmark(group, FakeChatTransport(), progress=False)
        with tempfile.TemporaryDirectory() as tmp:
            folder = write_report(
                Path(tmp),
                results,
                build_summary(results, warnings, dataset_sha="xyz", scenario_count=1),
            )
            self.assertTrue((folder / "summary.json").exists())
            with (folder / "manual_review.csv").open(encoding="utf-8-sig", newline="") as f:
                record = next(csv.DictReader(f))
            self.assertIn("language_score_0_to_3", record)
            self.assertEqual(record["language_score_0_to_3"], "")
            self.assertEqual(record["response"], "La robotique est votre intérêt.")

    def test_manual_scores_unfilled_are_not_invented(self):
        self.assertIsNone(grade(["", " "], "language"))
        with self.assertRaises(ValueError):
            grade(["4"], "language")

    def test_manual_aggregate_scored_rows_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "review.csv"
            with path.open("w", encoding="utf-8-sig", newline="") as f:
                fieldnames = ["language"] + [
                    f"{n}_score_0_to_3"
                    for n in ("language", "intent", "grounding", "memory", "safety")
                ]
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerow({"language": "arabizi", "language_score_0_to_3": "3"})
                writer.writerow({"language": "arabizi", "language_score_0_to_3": "1"})
            result = aggregate(path)
            self.assertEqual(result["dimensions"]["language"]["mean"], 2.0)
            self.assertEqual(result["dimensions"]["language"]["reviewed"], 2)
            self.assertIsNone(result["dimensions"]["intent"]["mean"])


class HttpTransportTests(unittest.TestCase):
    def test_real_http_contract_against_local_mock_server(self):
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        from threading import Thread

        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _respond(self, status, body=None):
                content = json.dumps(body).encode("utf-8") if body is not None else b""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def do_POST(self):
                if self.path == "/api/v1/visitor/sessions":
                    calls.append(("create",))
                    self._respond(201, {"id": "test-session-id", "token": "test-secret"})
                elif self.path == "/api/v1/visitor/sessions/test-session-id/chat":
                    data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    calls.append(("chat", self.headers.get("X-Visitor-Token"), data))
                    self._respond(
                        201,
                        {
                            "model": "http-stub-for-tests",
                            "user_message": {"sequence": 1},
                            "assistant_message": {"sequence": 2, "content": "Je peux vous aider."},
                        },
                    )
                else:
                    self._respond(404)

            def do_DELETE(self):
                calls.append(("delete", self.headers.get("X-Visitor-Token")))
                self._respond(204)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            transport = HttpChatTransport(f"http://127.0.0.1:{server.server_port}/api/v1")
            groups = selected_groups(
                load_cases(DEFAULT_DATASET), category="welcome", max_scenarios=1
            )
            results, warnings = run_benchmark(groups, transport, progress=False)
            self.assertEqual(results[0]["api_status"], "OK")
            self.assertEqual(results[0]["model"], "http-stub-for-tests")
            self.assertEqual(calls[0], ("create",))
            self.assertEqual(calls[1][1], "test-secret")
            self.assertEqual(calls[1][2], {"content": list(groups.values())[0][0]["prompt"]})
            self.assertEqual(calls[2], ("delete", "test-secret"))
            self.assertEqual(warnings, [])
            self.assertNotIn("test-secret", json.dumps(results))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
