"""SA-32 evaluation harness for the real SmartCampus AI HTTP chat API.

Uses Python standard library only, makes a fresh visitor session per scenario,
and deletes every session when finished. No fabricated LLM outputs.

Run from the repository root:
    python evaluation/run_eval.py --validate
    python evaluation/run_eval.py --smoke
    python evaluation/run_eval.py --all
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
import sys
import time
import unicodedata
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol
from urllib import error, request

DEFAULT_DATASET = Path(__file__).resolve().with_name("cases.jsonl")
DEFAULT_RESULTS_DIR = Path(__file__).resolve().with_name("results")
ALLOWED_LANGUAGES = {"fr", "derja", "arabizi", "mixed"}
ALLOWED_CATEGORIES = {
    "welcome",
    "intent",
    "profiling",
    "orientation",
    "reliability",
    "boundaries",
    "memory",
}
SMOKE_SCENARIOS = {
    "WELCOME-01",
    "WELCOME-02",
    "WELCOME-03",
    "INTENT-08",
    "RELIABILITY-01",
    "MEM-01",
    "MEM-03",
    "MEM-05",
}
CSV_COLUMNS = [
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
    "language_score_0_to_3",
    "intent_score_0_to_3",
    "grounding_score_0_to_3",
    "memory_score_0_to_3",
    "safety_score_0_to_3",
    "reviewer_notes",
]


class BenchmarkError(RuntimeError):
    """Validation or remote API error with no authentication secrets."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm(value: str) -> str:
    """Accent/case insensitive *lexical* comparison; no semantic grading."""
    base = unicodedata.normalize("NFKD", value).casefold()
    return "".join(c for c in base if not unicodedata.combining(c))


def load_cases(path: Path) -> list[dict[str, Any]]:
    """Strictly validate question data, multi-turn ordering, and expected checks."""
    cases: list[dict[str, Any]] = []
    ids: set[str] = set()
    scenarios: dict[str, list[int]] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise BenchmarkError(f"Invalid JSON at line {lineno}") from exc
        if not isinstance(row, dict):
            raise BenchmarkError(f"Expected JSON object at line {lineno}")
        mandatory_strings = (
            "case_id",
            "scenario_id",
            "language",
            "category",
            "prompt",
            "expected_behavior",
        )
        for name in mandatory_strings:
            if not isinstance(row.get(name), str) or not row[name].strip():
                raise BenchmarkError(f"Invalid {name} at line {lineno}")
        case_id = row["case_id"]
        if case_id in ids:
            raise BenchmarkError(f"Duplicate case_id: {case_id}")
        ids.add(case_id)
        if row["language"] not in ALLOWED_LANGUAGES:
            raise BenchmarkError(f"Invalid language: {case_id}")
        if row["category"] not in ALLOWED_CATEGORIES:
            raise BenchmarkError(f"Invalid category: {case_id}")
        if not isinstance(row.get("turn"), int) or isinstance(row["turn"], bool) or row["turn"] < 1:
            raise BenchmarkError(f"Invalid turn: {case_id}")
        if len(row["prompt"]) > 4000:
            raise BenchmarkError(f"Prompt is too long for backend: {case_id}")
        if not isinstance(row.get("review_criteria"), list) or not all(
            isinstance(c, str) and c.strip() for c in row["review_criteria"]
        ):
            raise BenchmarkError(f"Missing review_criteria: {case_id}")
        checks = row.get("checks")
        if not isinstance(checks, dict) or set(checks) - {
            "must_contain_any",
            "must_contain_all",
            "must_not_contain",
        }:
            raise BenchmarkError(f"Invalid checks: {case_id}")
        for key, anchors in checks.items():
            if (
                not isinstance(anchors, list)
                or not anchors
                or not all(isinstance(item, str) and item.strip() for item in anchors)
            ):
                raise BenchmarkError(f"Invalid anchors {key}: {case_id}")
        scenarios.setdefault(row["scenario_id"], []).append(row["turn"])
        cases.append(row)
    if not cases:
        raise BenchmarkError("Dataset is empty")
    for scenario, turns in scenarios.items():
        if turns != list(range(1, len(turns) + 1)):
            raise BenchmarkError(f"Scenario turns must be consecutive and ordered: {scenario}")
    return cases


def check_response(text: str, checks: dict[str, list[str]]) -> tuple[str, list[str]]:
    """Lexical anchors only. Not a substitute for linguistic/manual evaluation."""
    if not checks:
        return "REVIEW", []
    normalized = _norm(text)
    failed: list[str] = []
    any_terms = checks.get("must_contain_any", [])
    if any_terms and not any(_norm(term) in normalized for term in any_terms):
        failed.append("must_contain_any")
    for term in checks.get("must_contain_all", []):
        if _norm(term) not in normalized:
            failed.append(f"must_contain_all:{term}")
    for term in checks.get("must_not_contain", []):
        if _norm(term) in normalized:
            failed.append(f"must_not_contain:{term}")
    return ("FAIL" if failed else "PASS"), failed


class ChatTransport(Protocol):
    def create_session(self) -> dict[str, str]: ...
    def chat(self, session_id: str, token: str, prompt: str) -> dict[str, Any]: ...
    def delete_session(self, session_id: str, token: str) -> None: ...


class HttpChatTransport:
    """Calls the existing visitor routes; does not require an admin password."""

    def __init__(self, base_url: str, timeout: int = 360) -> None:
        self.base = base_url.rstrip("/") + "/visitor/sessions"
        self.timeout = timeout
        if not base_url.startswith(("http://127.0.0.1:", "http://localhost:")):
            raise BenchmarkError(
                "By default only localhost is allowed. Do not send evaluation data to an external API."
            )

    def _json(
        self, method: str, url: str, *, token: str | None = None, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        if token:
            headers["X-Visitor-Token"] = token
        payload = None
        if body is not None:
            payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = request.Request(url, data=payload, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                contents = response.read()
                return json.loads(contents) if contents else {}
        except error.HTTPError as exc:
            # Don't print raw upstream bodies, which could echo candidate input.
            raise BenchmarkError(f"Backend returned HTTP {exc.code} ({method})") from exc
        except (error.URLError, TimeoutError, OSError) as exc:
            raise BenchmarkError(
                f"Backend connection failed ({method}): {type(exc).__name__}"
            ) from exc
        except (ValueError, UnicodeDecodeError) as exc:
            raise BenchmarkError("Backend returned malformed JSON") from exc

    def create_session(self) -> dict[str, str]:
        session = self._json("POST", self.base)
        if not isinstance(session.get("id"), str) or not isinstance(session.get("token"), str):
            raise BenchmarkError("Session creation response missing id/token")
        return {"id": session["id"], "token": session["token"]}

    def chat(self, session_id: str, token: str, prompt: str) -> dict[str, Any]:
        return self._json(
            "POST", f"{self.base}/{session_id}/chat", token=token, body={"content": prompt}
        )

    def delete_session(self, session_id: str, token: str) -> None:
        self._json("DELETE", f"{self.base}/{session_id}", token=token)


def selected_groups(
    cases: list[dict[str, Any]],
    *,
    smoke: bool = False,
    max_scenarios: int | None = None,
    language: str | None = None,
    category: str | None = None,
    scenario_ids: list[str] | None = None,
) -> OrderedDict[str, list[dict[str, Any]]]:
    groups: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for case in cases:
        groups.setdefault(case["scenario_id"], []).append(case)
    if scenario_ids:
        missing = set(scenario_ids) - set(groups)
        if missing:
            raise BenchmarkError("Unknown scenario(s): " + ", ".join(sorted(missing)))
        groups = OrderedDict((key, val) for key, val in groups.items() if key in scenario_ids)
    if smoke:
        groups = OrderedDict((key, val) for key, val in groups.items() if key in SMOKE_SCENARIOS)
    if language:
        groups = OrderedDict(
            (key, val) for key, val in groups.items() if all(r["language"] == language for r in val)
        )
    if category:
        groups = OrderedDict(
            (key, val) for key, val in groups.items() if all(r["category"] == category for r in val)
        )
    if max_scenarios is not None:
        groups = OrderedDict(list(groups.items())[:max_scenarios])
    if not groups:
        raise BenchmarkError("No scenarios match your filter")
    return groups


def _blank_result(row: dict[str, Any], status: str, error_note: str = "") -> dict[str, Any]:
    return {
        "case_id": row["case_id"],
        "scenario_id": row["scenario_id"],
        "turn": row["turn"],
        "language": row["language"],
        "category": row["category"],
        "model": "",
        "prompt": row["prompt"],
        "response": "",
        "expected_behavior": row["expected_behavior"],
        "latency_seconds": None,
        "api_status": status,
        "auto_status": status,
        "auto_checks_failed": [],
        "language_score_0_to_3": "",
        "intent_score_0_to_3": "",
        "grounding_score_0_to_3": "",
        "memory_score_0_to_3": "",
        "safety_score_0_to_3": "",
        "reviewer_notes": error_note,
        "review_criteria": row["review_criteria"],
    }


def run_benchmark(
    groups: OrderedDict[str, list[dict[str, Any]]],
    transport: ChatTransport,
    *,
    progress: bool = True,
) -> tuple[list[dict[str, Any]], list[str]]:
    results: list[dict[str, Any]] = []
    cleanup_warnings: list[str] = []
    for index, (scenario_id, turns) in enumerate(groups.items(), 1):
        session: dict[str, str] | None = None
        if progress:
            print(f"[{index}/{len(groups)}] {scenario_id} ({len(turns)} turn(s))", flush=True)
        try:
            session = transport.create_session()
            for turn_index, row in enumerate(turns):
                started = time.perf_counter()
                try:
                    response = transport.chat(session["id"], session["token"], row["prompt"])
                    elapsed = round(time.perf_counter() - started, 2)
                    answer = response["assistant_message"]["content"]
                    user_seq = response["user_message"]["sequence"]
                    assistant_seq = response["assistant_message"]["sequence"]
                    if not isinstance(answer, str) or not answer.strip():
                        raise BenchmarkError("Empty assistant response")
                    if user_seq != row["turn"] * 2 - 1 or assistant_seq != row["turn"] * 2:
                        raise BenchmarkError("Unexpected DB message ordering")
                    status, failed = check_response(answer, row["checks"])
                    result = _blank_result(row, status)
                    result.update(
                        {
                            "api_status": "OK",
                            "auto_status": status,
                            "model": str(response.get("model", "")),
                            "response": answer,
                            "latency_seconds": elapsed,
                            "auto_checks_failed": failed,
                        }
                    )
                    results.append(result)
                    if progress:
                        print(f"    {row['case_id']}: {status} ({elapsed}s)", flush=True)
                except (BenchmarkError, KeyError, IndexError, TypeError, ValueError) as exc:
                    results.append(_blank_result(row, "ERROR", str(exc)))
                    for skipped in turns[turn_index + 1 :]:
                        results.append(_blank_result(skipped, "SKIPPED", "Prior turn failed"))
                    if progress:
                        print(f"    {row['case_id']}: ERROR — {exc}", flush=True)
                    break
        except (BenchmarkError, KeyError, TypeError) as exc:
            for row in turns:
                results.append(_blank_result(row, "ERROR", str(exc)))
            if progress:
                print(f"    Session creation failed: {exc}", flush=True)
        finally:
            if session:
                try:
                    transport.delete_session(session["id"], session["token"])
                except Exception as exc:
                    cleanup_warnings.append(
                        f"{scenario_id}: cleanup failed ({type(exc).__name__}); manual session purge may be needed"
                    )
    return results, cleanup_warnings


def build_summary(
    results: list[dict[str, Any]],
    cleanup_warnings: list[str],
    *,
    dataset_sha: str,
    scenario_count: int,
) -> dict[str, Any]:
    measured = [float(r["latency_seconds"]) for r in results if r["latency_seconds"] is not None]
    autos = Counter(r["auto_status"] for r in results)
    return {
        "generated_at_utc": utc_now(),
        "dataset_sha256": dataset_sha,
        "scenario_count": scenario_count,
        "case_count": len(results),
        "model_names": sorted({r["model"] for r in results if r["model"]}),
        "language_counts": dict(Counter(r["language"] for r in results)),
        "category_counts": dict(Counter(r["category"] for r in results)),
        "auto_status_counts": dict(autos),
        "automatic_anchor_accuracy": (
            round(autos.get("PASS", 0) / (autos.get("PASS", 0) + autos.get("FAIL", 0)), 4)
            if autos.get("PASS", 0) + autos.get("FAIL", 0)
            else None
        ),
        "latency_seconds_median": round(statistics.median(measured), 2) if measured else None,
        "latency_seconds_p95_nearest_rank": (
            sorted(measured)[max(0, (len(measured) * 95 + 99) // 100 - 1)] if measured else None
        ),
        "cleanup_warnings": cleanup_warnings,
        "limitations": [
            "Auto PASS is only lexical anchor matching, not factual or dialectal correctness.",
            "Open-ended responses require manual review (0-3 rubric).",
            "Comparisons require same dataset fingerprint and compatible inference settings.",
        ],
    }


def write_report(output_root: Path, results: list[dict[str, Any]], summary: dict[str, Any]) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")
    out = output_root / stamp
    out.mkdir(parents=True, exist_ok=False)
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with (out / "results.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        for row in results:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    # utf-8-sig enables French/Arabic in Excel on Windows without encoding errors.
    with (out / "manual_review.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(results)
    return out


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SA-32 SmartCampus AI real-chat evaluation")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--base-url", default="http://127.0.0.1:8001/api/v1")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--validate", action="store_true", help="Validate dataset without LLM calls")
    group.add_argument(
        "--smoke", action="store_true", help="Run a small multilingual live evaluation"
    )
    group.add_argument("--all", action="store_true", help="Run all 72 real model questions")
    parser.add_argument("--max-scenarios", type=int, help="Limit number of complete scenarios")
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Rerun exact scenario ID (repeatable). Full multi-turn scenario is always preserved.",
    )
    parser.add_argument("--language", choices=sorted(ALLOWED_LANGUAGES))
    parser.add_argument("--category", choices=sorted(ALLOWED_CATEGORIES))
    parser.add_argument("--timeout", type=int, default=360, help="HTTP timeout per model request")
    args = parser.parse_args(argv)
    if args.timeout < 10 or args.timeout > 1200:
        parser.error("--timeout must be between 10 and 1200 seconds")
    if args.max_scenarios is not None and args.max_scenarios < 1:
        parser.error("--max-scenarios must be >=1")
    if args.scenario and args.smoke:
        parser.error("Use --all with --scenario; targeted reruns are not smoke runs")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        cases = load_cases(args.dataset)
        sha = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
        print(
            f"Dataset validated: {len(cases)} cases, "
            f"{len({row['scenario_id'] for row in cases})} scenarios, SHA256 {sha[:12]}"
        )
        if args.validate:
            print("No model calls were made.")
            return 0
        groups = selected_groups(
            cases,
            smoke=args.smoke,
            max_scenarios=args.max_scenarios,
            language=args.language,
            category=args.category,
            scenario_ids=args.scenario,
        )
        transport = HttpChatTransport(args.base_url, timeout=args.timeout)
        print(
            f"Running {sum(map(len, groups.values()))} live turns across {len(groups)} isolated sessions."
        )
        results, warnings = run_benchmark(groups, transport)
        summary = build_summary(results, warnings, dataset_sha=sha, scenario_count=len(groups))
        location = write_report(args.output_dir, results, summary)
        print(f"Results: {location}")
        print(f"Auto status: {summary['auto_status_counts']} (manual review still required)")
        if warnings:
            print("WARNING: some visitor sessions could not be deleted; see summary.json")
        return 1 if (summary["auto_status_counts"].get("ERROR", 0) or warnings) else 0
    except (BenchmarkError, OSError, UnicodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
