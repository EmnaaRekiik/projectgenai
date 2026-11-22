"""Show where the live OpenAPI schema differs from docs/openapi_snapshot.json, and the library versions.

Run from the project root:  python scripts/openapi_diff.py
"""
import json
import sys
from importlib.metadata import version
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app  # noqa: E402


def strip_decimal_patterns(node):
    """Same normalisation as tests/test_openapi_contract.py (Decimal regex differs by Pydantic version)."""
    if isinstance(node, dict):
        return {k: strip_decimal_patterns(v) for k, v in node.items()
                if not (k == "pattern" and isinstance(v, str) and v.startswith("^(?!^[-+.]*$)"))}
    if isinstance(node, list):
        return [strip_decimal_patterns(i) for i in node]
    return node


def walk(live, ref, path, out):
    if isinstance(live, dict) and isinstance(ref, dict):
        for key in sorted(set(live) | set(ref)):
            if key not in live:
                out.append((path + "/" + key, "missing in live schema", ref[key]))
            elif key not in ref:
                out.append((path + "/" + key, live[key], "missing in snapshot"))
            else:
                walk(live[key], ref[key], path + "/" + key, out)
    elif isinstance(live, list) and isinstance(ref, list) and len(live) == len(ref):
        for i, (a, b) in enumerate(zip(live, ref)):
            walk(a, b, f"{path}[{i}]", out)
    elif live != ref:
        out.append((path, live, ref))


snapshot = json.loads(Path(__file__).resolve().parents[1].joinpath("docs", "openapi_snapshot.json").read_text(encoding="utf-8"))
diffs = []
walk(strip_decimal_patterns(app.openapi()), strip_decimal_patterns(snapshot), "", diffs)
print("Versions:", {p: version(p) for p in ("fastapi", "pydantic", "starlette")}, "python", sys.version.split()[0])
print("Identical" if not diffs else f"{len(diffs)} difference(s); first 12:")
for path, live, ref in diffs[:12]:
    print(f"- {path}\n    live:     {live}\n    snapshot: {ref}")
