"""Detect accidental changes to the documented Swagger API contract."""

import json
from pathlib import Path

from app.main import app


def test_generated_openapi_matches_reviewed_snapshot():
    snapshot = Path(__file__).resolve().parents[1] / "docs" / "openapi_snapshot.json"
    reviewed_contract = json.loads(snapshot.read_text(encoding="utf-8"))
    assert app.openapi() == reviewed_contract
