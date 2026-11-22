"""Regression test for the *real* FastAPI DB dependency (not overridden in conftest)."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import session as db_session
from app.db.base import Base
from app.main import app
from app.models import Institution, Program  # noqa: F401


def test_health_ready_uses_a_real_db_session(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    # Do not override FastAPI's get_db dependency: catch factory invocation errors.
    monkeypatch.setattr(db_session, "get_session_factory", lambda: factory)
    app.dependency_overrides.pop(db_session.get_db, None)
    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/health/ready")
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "ready"
    finally:
        engine.dispose()
