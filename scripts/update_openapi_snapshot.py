"""Regenerate docs/openapi_snapshot.json from the live application (run after any API change).

    python scripts/update_openapi_snapshot.py

Then run: python -m pytest tests/test_openapi_contract.py -q, and review the diff in git before committing.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.main import app  # noqa: E402

target = ROOT / "docs" / "openapi_snapshot.json"
target.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {target} ({len(app.openapi()['paths'])} paths)")
