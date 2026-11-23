"""T10: compare several LLM runs (same dataset, same conditions) from their manual_review.csv files.

Expected layout, produced by scripts/benchmark_models.ps1:
    evaluation/results/<profile>/<timestamp>/manual_review.csv   (+ summary.json)

Usage:
    python evaluation/compare_models.py
    python evaluation/compare_models.py --results-dir evaluation/results --profiles evaluation/models.json

Only measured values are reported. Human scores are averaged over the answers a reviewer actually filled in
(and the number is shown); missing prices give "n/a" instead of a guessed cost.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

DIMENSIONS = ["language", "intent", "grounding", "memory", "safety"]
DEFAULT_RESULTS = Path(__file__).resolve().with_name("results")
CHARS_PER_TOKEN = 4  # rough rule of thumb, only used for the cost ESTIMATE


def p95(values: list[float]) -> float | None:
    """Nearest-rank 95th percentile (same definition as run_eval.py)."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, (len(ordered) * 95 + 99) // 100 - 1)]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def discover(results_dir: Path) -> dict[str, list[Path]]:
    """profile name -> list of run directories containing manual_review.csv."""
    found: dict[str, list[Path]] = {}
    if not results_dir.is_dir():
        return found
    for profile_dir in sorted(p for p in results_dir.iterdir() if p.is_dir()):
        runs = sorted(r for r in profile_dir.iterdir() if (r / "manual_review.csv").is_file())
        if runs:
            found[profile_dir.name] = runs
    return found


def _score(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    if value not in {"0", "1", "2", "3"}:
        raise ValueError(f"Human score must be an integer from 0 to 3, got {value!r}")
    return int(value)


def summarize_profile(
    name: str, runs: list[Path], profile_cfg: dict[str, Any] | None
) -> dict[str, Any]:
    latencies: list[float] = []
    run_medians: list[float] = []
    statuses: dict[str, int] = defaultdict(int)
    autos: dict[str, int] = defaultdict(int)
    scores: dict[str, list[int]] = {d: [] for d in DIMENSIONS}
    per_language: dict[str, list[float]] = defaultdict(list)
    models: set[str] = set()
    in_chars = out_chars = 0
    dataset_hashes: set[str] = set()
    for run in runs:
        summary_path = run / "summary.json"
        if summary_path.is_file():
            dataset_hashes.add(
                json.loads(summary_path.read_text(encoding="utf-8")).get("dataset_sha256", "")
            )
        this_run: list[float] = []
        for row in read_rows(run / "manual_review.csv"):
            statuses[row["api_status"]] += 1
            autos[row["auto_status"]] += 1
            if row["api_status"] == "OK":
                if row.get("model"):
                    models.add(row["model"])
                if row["latency_seconds"]:
                    value = float(row["latency_seconds"])
                    latencies.append(value)
                    this_run.append(value)
                    per_language[row["language"]].append(value)
                in_chars += len(row["prompt"])
                out_chars += len(row["response"])
            for dim in DIMENSIONS:
                score = _score(row.get(f"{dim}_score_0_to_3", ""))
                if score is not None:
                    scores[dim].append(score)
        if this_run:
            run_medians.append(statistics.median(this_run))
    calls = sum(v for k, v in statuses.items() if k != "SKIPPED")
    passed, failed = autos.get("PASS", 0), autos.get("FAIL", 0)
    dim_means = {d: _mean(v) for d, v in scores.items()}
    available = [m for m in dim_means.values() if m is not None]
    price_in = (profile_cfg or {}).get("price_per_million_input_usd")
    price_out = (profile_cfg or {}).get("price_per_million_output_usd")
    cost = None
    if price_in is not None and price_out is not None:
        cost = round(
            in_chars / CHARS_PER_TOKEN / 1e6 * price_in
            + out_chars / CHARS_PER_TOKEN / 1e6 * price_out,
            4,
        )
    return {
        "profile": name,
        "model": ", ".join(sorted(models)) or (profile_cfg or {}).get("model", ""),
        "runs": len(runs),
        "calls": calls,
        "ok": statuses.get("OK", 0),
        "ok_rate": round(statuses.get("OK", 0) / calls, 4) if calls else None,
        "errors": statuses.get("ERROR", 0),
        "latency_mean_s": round(statistics.mean(latencies), 2) if latencies else None,
        "latency_median_s": round(statistics.median(latencies), 2) if latencies else None,
        "latency_p95_s": p95(latencies),
        "run_median_min_s": round(min(run_medians), 2) if run_medians else None,
        "run_median_max_s": round(max(run_medians), 2) if run_medians else None,
        "latency_median_by_language_s": {
            k: round(statistics.median(v), 2) for k, v in sorted(per_language.items())
        },
        "anchor_accuracy": round(passed / (passed + failed), 4) if passed + failed else None,
        "human_means": dim_means,
        "human_overall_mean_0_to_3": _mean(available),
        "human_scored_answers": max((len(v) for v in scores.values()), default=0),
        "estimated_cost_usd": cost,
        "dataset_hashes": sorted(h for h in dataset_hashes if h),
    }


def compare(results_dir: Path, profiles_file: Path | None) -> dict[str, Any]:
    cfg: dict[str, dict[str, Any]] = {}
    if profiles_file and profiles_file.is_file():
        for item in json.loads(profiles_file.read_text(encoding="utf-8")).get("profiles", []):
            cfg[item["name"]] = item
    runs = discover(results_dir)
    if not runs:
        raise SystemExit(
            f"No run found in {results_dir}. Expected <profile>/<timestamp>/manual_review.csv"
        )
    rows = [summarize_profile(name, paths, cfg.get(name)) for name, paths in runs.items()]
    warnings: list[str] = []
    hashes = {h for r in rows for h in r["dataset_hashes"]}
    if len(hashes) > 1:
        warnings.append(
            "Les profils n'ont pas été évalués avec le même jeu de questions : comparaison INVALIDE."
        )
    for r in rows:
        if r["human_scored_answers"] == 0:
            warnings.append(
                f"{r['profile']}: aucune note humaine saisie (colonnes *_score_0_to_3 vides)."
            )
        if r["runs"] < 3:
            warnings.append(
                f"{r['profile']}: {r['runs']} répétition(s) seulement (3 recommandées pour la variabilité)."
            )
        if r["errors"]:
            warnings.append(f"{r['profile']}: {r['errors']} appel(s) en erreur.")
    return {"profiles": rows, "warnings": warnings}


def _fmt(value: Any, suffix: str = "") -> str:
    return "n/a" if value is None else f"{value}{suffix}"


def to_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Comparaison des modèles (T10)",
        "",
        "| Profil | Modèle | Appels | Réussite | Latence médiane | P95 | Ancres auto | Qualité humaine /3 | Réponses notées | Coût estimé (USD) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in result["profiles"]:
        ok = "n/a" if r["ok_rate"] is None else f"{r['ok_rate'] * 100:.1f} %"
        anchors = "n/a" if r["anchor_accuracy"] is None else f"{r['anchor_accuracy'] * 100:.0f} %"
        lines.append(
            f"| {r['profile']} | {r['model']} | {r['calls']} | {ok} | {_fmt(r['latency_median_s'], ' s')} | "
            f"{_fmt(r['latency_p95_s'], ' s')} | {anchors} | {_fmt(r['human_overall_mean_0_to_3'])} | "
            f"{r['human_scored_answers']} | {_fmt(r['estimated_cost_usd'])} |"
        )
    lines += [
        "",
        "## Notes humaines par dimension (0 à 3)",
        "",
        "| Profil | " + " | ".join(DIMENSIONS) + " |",
        "|---|" + "---|" * len(DIMENSIONS),
    ]
    for r in result["profiles"]:
        lines.append(
            f"| {r['profile']} | "
            + " | ".join(_fmt(r["human_means"][d]) for d in DIMENSIONS)
            + " |"
        )
    lines += [
        "",
        "## Latence médiane par langue",
        "",
        "| Profil | fr | derja | arabizi | mixed |",
        "|---|---|---|---|---|",
    ]
    for r in result["profiles"]:
        by = r["latency_median_by_language_s"]
        lines.append(
            f"| {r['profile']} | "
            + " | ".join(_fmt(by.get(k), " s") for k in ("fr", "derja", "arabizi", "mixed"))
            + " |"
        )
    lines += ["", "## Avertissements", ""]
    lines += [f"- {w}" for w in result["warnings"]] or ["- Aucun."]
    lines += [
        "",
        "## Limites",
        "",
        "- Les notes humaines sont subjectives : indiquer qui a relu et selon quelle grille (0 à 3).",
        "- Les « ancres auto » ne vérifient que la présence de mots attendus, pas l'exactitude.",
        "- Le coût est une **estimation basse** (1 jeton ≈ 4 caractères, sans historique ni consigne système) et seulement calculé si les prix du profil sont renseignés.",
        "- Une comparaison n'est valable que si tous les profils ont reçu le même jeu de questions dans les mêmes conditions.",
    ]
    return "\n".join(lines) + "\n"


def write_csv(path: Path, result: dict[str, Any]) -> None:
    fields = [
        "profile",
        "model",
        "runs",
        "calls",
        "ok",
        "ok_rate",
        "errors",
        "latency_mean_s",
        "latency_median_s",
        "latency_p95_s",
        "run_median_min_s",
        "run_median_max_s",
        "anchor_accuracy",
        "human_overall_mean_0_to_3",
        "human_scored_answers",
        "estimated_cost_usd",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields + [f"human_{d}" for d in DIMENSIONS], extrasaction="ignore"
        )
        writer.writeheader()
        for r in result["profiles"]:
            writer.writerow({**r, **{f"human_{d}": r["human_means"][d] for d in DIMENSIONS}})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument(
        "--profiles", type=Path, default=Path(__file__).resolve().with_name("models.json")
    )
    args = parser.parse_args(argv)
    result = compare(args.results_dir, args.profiles)
    (args.results_dir / "comparison.md").write_text(to_markdown(result), encoding="utf-8")
    write_csv(args.results_dir / "comparison.csv", result)
    (args.results_dir / "comparison.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(to_markdown(result))
    print(f"Écrit : {args.results_dir / 'comparison.md'}, comparison.csv, comparison.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
