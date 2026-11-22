import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_sqlite_is_rejected_in_runtime_settings():
    with pytest.raises(ValidationError, match="SQLite not allowed"):
        Settings(database_url="sqlite:///oops.db", admin_api_key=None)


def test_admin_key_minimum_length():
    with pytest.raises(ValidationError, match="at least 32"):
        Settings(database_url="postgresql+psycopg://u:p@db:5432/test", admin_api_key="short")


def test_missing_bootstrap_key_disables_bootstrap_access(client, institution):
    from app.core.config import Settings, get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql+psycopg://u:p@db:5432/test", admin_api_key=None
    )
    result = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "email": "foo@example.org",
            "display_name": "Foo Admin",
            "password": "Strong password 987654",
            "role": "PLATFORM_ADMIN",
        },
        headers={"X-Admin-Key": "x" * 40},
    )
    assert result.status_code == 503


def test_special_characters_in_db_password_are_preserved():
    cfg = Settings(
        database_url=None,
        db_host="db", db_user="demo", db_password="p@ss:/#word",
        db_name="smartcampus", admin_api_key=None,
    )
    assert cfg.sqlalchemy_url.password == "p@ss:/#word"
    assert cfg.sqlalchemy_url.drivername == "postgresql+psycopg"


def test_default_placeholder_admin_key_is_rejected():
    with pytest.raises(ValidationError, match="placeholder must be replaced"):
        Settings(
            database_url="postgresql+psycopg://u:p@db:5432/test",
            admin_api_key="REPLACE_WITH_A_DIFFERENT_RANDOM_KEY_AT_LEAST_32_CHARACTERS",
        )
