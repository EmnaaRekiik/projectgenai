"""Aggregate human-reviewed SA-32 answers; never invent missing human scores.

Usage: python evaluation/score_reviews.py evaluation/results/<run>/manual_review.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

DIMENSIONS = ["language", "intent", "grounding", "memory", "safety"]


def grade(values: list[str], dimension: str) -> float | None:
    valid = []
    for value in values:
        if not value.strip():
            continue
        try:
            score = int(value)
        except ValueError as exc:
            raise ValueError(f"Invalid manual score for {dimension}: {value!r}") from exc
        if score not in (0, 1, 2, 3) or str(score) != value.strip():
            raise ValueError(f"Scores must be integers 0-3 for {dimension}")
        valid.append(score)
    return round(sum(valid) / len(valid), 3) if valid else None


def aggregate(path: Path) -> dict:
    with path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError("No evaluation rows to score")
    out = {"source": str(path), "rows": len(rows), "dimensions": {}, "per_language": {}}
    for dim in DIMENSIONS:
        col = f"{dim}_score_0_to_3"
        values = [r.get(col, "") for r in rows]
        if any(v is None for v in values):
            raise ValueError(f"Missing required score column: {col}")
        out["dimensions"][dim] = {
            "mean": grade(values, dim),
            "reviewed": sum(1 for v in values if v.strip()),
        }
    langs = defaultdict(list)
    for row in rows:
        langs[row["language"]].append(row)
    for lang, subset in sorted(langs.items()):
        out["per_language"][lang] = {
            dim: {
                "mean": grade([r[f"{dim}_score_0_to_3"] for r in subset], dim),
                "reviewed": sum(1 for r in subset if r[f"{dim}_score_0_to_3"].strip()),
            }
            for dim in DIMENSIONS
        }
    out["warning"] = (
        "Human scores are subjective; report the number of reviewed answers and evaluator protocol."
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()
    print(json.dumps(aggregate(args.csv_file), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
