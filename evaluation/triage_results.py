"""Inspect an already-saved SA-32 evaluation run without making any LLM calls.

Usage:
    python evaluation/triage_results.py --run evaluation/results/20261120T144641_548403Z

Read-only except for writing a triage.md report inside the selected run directory.
No benchmark results or manual grades are changed.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().with_name("results")
PRIORITY_CATEGORIES = ("reliability", "boundaries", "memory")


def load_run(folder: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not folder.is_dir():
        raise ValueError(f"Result directory does not exist: {folder}")
    results_file = folder / "results.jsonl"
    summary_file = folder / "summary.json"
    if not results_file.is_file() or not summary_file.is_file():
        raise ValueError("Result directory must contain results.jsonl and summary.json")
    rows = []
    for number, line in enumerate(results_file.read_text(encoding="utf-8-sig").splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on result line {number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"Non-object result on line {number}")
            rows.append(row)
    summary = json.loads(summary_file.read_text(encoding="utf-8-sig"))
    if not rows or not isinstance(summary, dict):
        raise ValueError("Missing or invalid evaluation results")
    return rows, summary


def latest_run(root: Path = ROOT) -> Path:
    if not root.is_dir():
        raise ValueError(f"No results directory: {root}")
    runs = sorted((p for p in root.iterdir() if p.is_dir() and (p / "results.jsonl").is_file()), reverse=True)
    if not runs:
        raise ValueError(f"No evaluation runs found in {root}")
    return runs[0]


def _md_value(value: Any) -> str:
    """Prevent synthetic prompt text from introducing unintended Markdown layout."""
    value = str(value or "").replace("\r", " ").replace("\n", " ")
    return value.replace("|", "\\|").replace("`", "'")


def make_report(rows: list[dict[str, Any]], summary: dict[str, Any],
                folder: Path) -> str:
    counts = Counter(str(row.get("auto_status", "UNKNOWN")) for row in rows)
    completed = sum(counts[s] for s in ("PASS", "FAIL", "REVIEW"))
    recall = [row for row in rows if row.get("category") == "memory" and row.get("turn") == 2]
    scored_recall = [row for row in recall if row.get("auto_status") in {"PASS", "FAIL"}]
    passed_recall = sum(row.get("auto_status") == "PASS" for row in scored_recall)
    denominator = len(scored_recall)
    pct = f"{passed_recall/denominator:.1%}" if denominator else "N/A"
    lines = [
        "# SmartCampus AI — Live evaluation triage",
        "",
        f"Original run folder: `{folder.name}`",
        f"Dataset SHA256: `{summary.get('dataset_sha256', 'not recorded')}`",
        "",
        "## Verified automatic results (not a model-quality score)",
        "",
        f"- Evaluated dataset rows: {len(rows)}",
        f"- Successful API responses: {completed}",
        f"- REVIEW: {counts['REVIEW']} | PASS: {counts['PASS']} | FAIL: {counts['FAIL']} | ERROR: {counts['ERROR']} | SKIPPED: {counts['SKIPPED']}",
        f"- Lexical recall checks: {passed_recall}/{denominator} passed ({pct}); inconclusive or missing recalls excluded",
        "- A lexical FAIL may be a correct paraphrase. A lexical PASS is not proof of semantic correctness.",
        "- A 502 is an availability failure, not a memory-answer failure. Dependent SKIPPED turns are not scored.",
        "",
        "## Follow-up: non-PASS cases needing immediate investigation",
        "",
    ]
    problems = [row for row in rows if row.get("auto_status") in {"FAIL", "ERROR", "SKIPPED"}]
    if not problems:
        lines.append("No automatic FAIL/ERROR/SKIPPED cases in this run.")
    for row in problems:
        status = row.get("auto_status", "UNKNOWN")
        lines.extend([
            f"### {_md_value(row.get('case_id', 'unknown'))} — {status}",
            "",
            f"Language / category: `{_md_value(row.get('language'))}` / `{_md_value(row.get('category'))}`",
            "",
            f"Prompt: {_md_value(row.get('prompt'))}",
            "",
            f"Expected behavior: {_md_value(row.get('expected_behavior'))}",
            "",
            f"Actual response: {_md_value(row.get('response')) or '(none returned)' }",
            "",
            f"Automatic failed checks: `{json.dumps(row.get('auto_checks_failed', []), ensure_ascii=False)}`",
            "",
            f"Recorded note: {_md_value(row.get('reviewer_notes')) or '(none)' }",
            "",
        ])
    lines.extend([
        "## Manual review priority (edit the ORIGINAL manual_review.csv)",
        "",
        "First review completed responses in these categories:",
        "",
    ])
    for category in PRIORITY_CATEGORIES:
        subset = [row for row in rows if row.get("category") == category and row.get("auto_status") not in {"ERROR", "SKIPPED"}]
        lines.append(f"- {category}: {len(subset)} completed responses to assess")
    lines.extend([
        "",
        "Suggested review sequence: memory recall failures, reliability questions, admission boundaries, other memory recalls, then welcome/intent/profiling/orientation.",
        "",
        "**Do not change the original `results.jsonl`, `summary.json` or dataset after seeing these results.**",
        "Any focused rerun belongs to a new result folder and should be reported separately.",
        "",
        "## Commands (run from project root)",
        "",
        "```powershell",
        "# Re-run only the original two-turn scenarios. No other cases are repeated.",
        "python evaluation/run_eval.py --all --scenario MEM-06 --scenario MEM-10",
        "# Grade the original full run after manually filling its CSV:",
        f'python evaluation/score_reviews.py "evaluation/results/{folder.name}/manual_review.csv"',
        "```",
        "",
    ])
    warnings = summary.get("cleanup_warnings") or []
    if warnings:
        lines.extend(["## Session cleanup warnings", ""])
        lines.extend(f"- {_md_value(item)}" for item in warnings)
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only inspection of a finished SA-32 evaluation")
    parser.add_argument("--run", type=Path, help="Directory containing results.jsonl and summary.json; defaults to latest")
    args = parser.parse_args(argv)
    try:
        folder = args.run if args.run else latest_run()
        rows, summary = load_run(folder)
        report = make_report(rows, summary, folder)
        destination = folder / "triage.md"
        destination.write_text(report, encoding="utf-8")
        issues = [r for r in rows if r.get("auto_status") in {"FAIL", "ERROR", "SKIPPED"}]
        counts = Counter(str(r.get("auto_status", "UNKNOWN")) for r in rows)
        print(f"Original run: {folder}")
        print(f"Statuses: {dict(counts)}")
        for row in issues:
            print(f"{row.get('case_id')}: {row.get('auto_status')}")
            if row.get("response"):
                print(f"  Actual answer: {str(row['response']).replace(chr(10), ' ')[:1200]}")
            if row.get("auto_checks_failed"):
                print(f"  Lexical check: {row['auto_checks_failed']}")
            if row.get("reviewer_notes"):
                print(f"  Note: {row['reviewer_notes']}")
        print(f"Wrote: {destination}")
        print("No API calls made. Original benchmark outputs were not changed.")
        return 0
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
