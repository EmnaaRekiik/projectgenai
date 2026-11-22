"""Guards against mistakes that SQLite hides but PostgreSQL rejects at startup."""

import re
from pathlib import Path

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base

VERSIONS = Path(__file__).resolve().parents[1] / "migrations" / "versions"


def test_alembic_revision_ids_fit_the_32_character_version_column():
    # alembic_version.version_num is VARCHAR(32): a longer id makes `alembic upgrade` fail on PostgreSQL.
    for path in VERSIONS.glob("*.py"):
        revision = re.search(
            r'^revision = "([^"]+)"', path.read_text(encoding="utf-8"), re.M
        ).group(1)
        assert len(revision) <= 32, (
            f"{path.name}: revision id '{revision}' is {len(revision)} characters"
        )


def test_migration_chain_is_linear_without_gaps():
    revisions, parents = set(), []
    for path in VERSIONS.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        revisions.add(re.search(r'^revision = "([^"]+)"', text, re.M).group(1))
        parents.append(re.search(r'^down_revision = (?:"([^"]+)"|None)', text, re.M).group(1))
    assert parents.count(None) == 1, "exactly one root migration expected"
    assert all(parent in revisions for parent in parents if parent), (
        "a migration points to a missing parent"
    )
    assert len([p for p in parents if p]) == len(set(p for p in parents if p)), (
        "branching migrations"
    )


def test_constraint_and_index_names_fit_postgresql_63_character_limit():
    for table in Base.metadata.tables.values():
        names = [c.name for c in table.constraints if c.name] + [
            i.name for i in table.indexes if i.name
        ]
        for name in names:
            assert len(name) <= 63, f"{table.name}: '{name}' exceeds 63 characters"
