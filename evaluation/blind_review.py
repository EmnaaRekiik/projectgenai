"""Blind side-by-side human review for T10 (the reviewer does not see which model wrote which answer).

1. prepare  : build evaluation/results/blind_review.csv (answers A/B/C shuffled per question) and blind_key.json
2. (human)  : open blind_review.csv in Excel and fill the score columns (0-3, empty = cannot judge)
3. merge    : copy the scores back into each model's manual_review.csv, then run compare_models.py

    python evaluation/blind_review.py prepare
    python evaluation/blind_review.py merge

Scores are never invented: an empty cell stays empty, anything other than 0, 1, 2 or 3 stops the merge.
Save the file from Excel as "CSV UTF-8" so Arabic text is kept.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import shutil
import sys
from pathlib import Path

try:  # works as a script and as a module
    from compare_models import DIMENSIONS, discover, read_rows
except ImportError:  # pragma: no cover
    from evaluation.compare_models import DIMENSIONS, discover, read_rows

LABELS = "ABCDEFGH"
BACKUP_SUFFIX = ".before_blind_merge"


def _pick_run(runs: list[Path], which: str) -> Path:
    return runs[0] if which == "first" else runs[-1]


def prepare(
    results_dir: Path, profiles: list[str] | None, which: str, seed: int, delimiter: str
) -> tuple[Path, Path]:
    found = discover(results_dir)
    names = profiles or sorted(found)
    missing = [n for n in names if n not in found]
    if missing:
        raise SystemExit(f"No results for: {', '.join(missing)}")
    if len(names) < 2:
        raise SystemExit("A blind comparison needs at least two profiles.")
    if len(names) > len(LABELS):
        raise SystemExit(f"At most {len(LABELS)} profiles are supported.")
    runs = {name: _pick_run(found[name], which) for name in names}
    rows = {
        name: {r["case_id"]: r for r in read_rows(runs[name] / "manual_review.csv")}
        for name in names
    }
    common = [cid for cid in rows[names[0]] if all(cid in rows[n] for n in names)]
    if not common:
        raise SystemExit("The profiles share no case.")
    first_turn_prompt = {}
    for row in rows[names[0]].values():
        if row.get("turn") == "1":
            first_turn_prompt[row["scenario_id"]] = row["prompt"]
    rng = random.Random(seed)
    labels = LABELS[: len(names)]
    key: dict[str, dict[str, str]] = {}
    out_rows = []
    for cid in common:
        order = list(names)
        rng.shuffle(order)
        key[cid] = {label: profile for label, profile in zip(labels, order)}
        base = rows[names[0]][cid]
        entry = {
            "case_id": cid,
            "language": base.get("language", ""),
            "category": base.get("category", ""),
            "context_previous_user_message": first_turn_prompt.get(base.get("scenario_id", ""), "")
            if base.get("turn") != "1"
            else "",
            "prompt": base.get("prompt", ""),
            "expected_behavior": base.get("expected_behavior", ""),
        }
        for label in labels:
            entry[f"response_{label}"] = rows[key[cid][label]][cid].get("response", "")
        for label in labels:
            for dim in DIMENSIONS:
                entry[f"{label}_{dim}"] = ""
        entry["reviewer_notes"] = ""
        out_rows.append(entry)
    csv_path = results_dir / "blind_review.csv"
    key_path = results_dir / "blind_key.json"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(out_rows[0]), delimiter=delimiter)
        writer.writeheader()
        writer.writerows(out_rows)
    key_path.write_text(
        json.dumps(
            {"seed": seed, "runs": {n: str(p) for n, p in runs.items()}, "labels": key},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return csv_path, key_path


def _read_filled(path: Path) -> list[dict[str, str]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SystemExit(
            "The file is not UTF-8. In Excel use 'Save as > CSV UTF-8' so Arabic text is preserved."
        ) from exc
    header = text.splitlines()[0] if text else ""
    delimiter = ";" if header.count(";") >= header.count(",") else ","
    return list(csv.DictReader(text.splitlines(), delimiter=delimiter))


def _valid(value: str, where: str) -> str:
    value = (value or "").strip()
    if value == "":
        return ""
    if value not in {"0", "1", "2", "3"}:
        raise SystemExit(
            f"Invalid score {value!r} at {where}: only 0, 1, 2, 3 or empty are accepted."
        )
    return value


def merge(results_dir: Path, filled: Path | None) -> dict[str, int]:
    key_path = results_dir / "blind_key.json"
    filled = filled or results_dir / "blind_review.csv"
    if not key_path.is_file() or not filled.is_file():
        raise SystemExit("Run 'prepare' first (blind_review.csv and blind_key.json are missing).")
    meta = json.loads(key_path.read_text(encoding="utf-8"))
    labels_by_case = meta["labels"]
    scores: dict[str, dict[str, dict[str, str]]] = {name: {} for name in meta["runs"]}
    for row in _read_filled(filled):
        cid = row.get("case_id", "")
        if cid not in labels_by_case:
            raise SystemExit(f"Unknown case_id {cid!r}: was the file made from another 'prepare'?")
        for label, profile in labels_by_case[cid].items():
            values = {
                dim: _valid(row.get(f"{label}_{dim}", ""), f"{cid} {label}_{dim}")
                for dim in DIMENSIONS
            }
            scores[profile][cid] = values
    written: dict[str, int] = {}
    for profile, run_dir in meta["runs"].items():
        path = Path(run_dir) / "manual_review.csv"
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if not backup.exists():
            shutil.copy2(path, backup)
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            fieldnames = list(reader.fieldnames or [])
            data = list(reader)
        count = 0
        for row in data:
            values = scores[profile].get(row["case_id"])
            if values is None:
                continue
            for dim, value in values.items():
                row[f"{dim}_score_0_to_3"] = value
            count += sum(1 for v in values.values() if v != "")
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        written[profile] = count
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--results-dir", type=Path, default=Path("evaluation/results"))
    prep.add_argument("--profiles", nargs="*", help="profile names (default: all found)")
    prep.add_argument(
        "--which", choices=["first", "last"], default="first", help="which repetition to review"
    )
    prep.add_argument("--seed", type=int, default=2026)
    prep.add_argument("--delimiter", default=";", help="';' for Excel in French, ',' otherwise")
    mrg = sub.add_parser("merge")
    mrg.add_argument("--results-dir", type=Path, default=Path("evaluation/results"))
    mrg.add_argument("--file", type=Path, help="filled CSV (default: results/blind_review.csv)")
    args = parser.parse_args(argv)
    if args.command == "prepare":
        csv_path, key_path = prepare(
            args.results_dir, args.profiles, args.which, args.seed, args.delimiter
        )
        print(f"Wrote {csv_path}\nWrote {key_path} (do NOT open it before scoring)")
    else:
        written = merge(args.results_dir, args.file)
        for profile, count in written.items():
            print(f"{profile}: {count} score(s) copied")
        print("Next: python evaluation/compare_models.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
