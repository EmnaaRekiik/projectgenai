"""Detect accidental changes to the documented Swagger API contract."""

import json
from pathlib import Path

from app.main import app

# Pydantic's JSON schema for Decimal fields embeds a generated regular expression whose presence
# and exact text depend on the Pydantic version (2.13 emits it, 2.14 does not). It carries no
# information beyond the `max_digits` / `decimal_places` rules, so it is ignored when comparing;
# every other schema detail is still compared exactly.
DECIMAL_PATTERN_PREFIX = "^(?!^[-+.]*$)"


def without_decimal_patterns(node):
    if isinstance(node, dict):
        return {
            key: without_decimal_patterns(value)
            for key, value in node.items()
            if not (
                key == "pattern"
                and isinstance(value, str)
                and value.startswith(DECIMAL_PATTERN_PREFIX)
            )
        }
    if isinstance(node, list):
        return [without_decimal_patterns(item) for item in node]
    return node


def test_generated_openapi_matches_reviewed_snapshot():
    snapshot = Path(__file__).resolve().parents[1] / "docs" / "openapi_snapshot.json"
    reviewed_contract = json.loads(snapshot.read_text(encoding="utf-8"))
    assert without_decimal_patterns(app.openapi()) == without_decimal_patterns(reviewed_contract)
