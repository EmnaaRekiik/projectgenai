"""Scheduled purge implementation; same logic runs in dedicated Docker worker."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.passwords import hash_password
from app.auth.tokens import digest_token
from app.db import purge_expired as cleanup
from app.models.candidate import CandidateEmailToken, CandidateSession, CandidateUser
from app.models.rate_limit import RateLimitBucket


def test_retention_removes_expired_candidate_tokens_and_buckets(client, test_engine, monkeypatch):
    now = datetime.now(timezone.utc)
    with Session(test_engine) as db:
        user = CandidateUser(
            email="old@example.org",
            display_name="Old",
            password_hash=hash_password("long-password-123456"),
            interests="[]",
            is_active=True,
            failed_login_count=0,
        )
        db.add(user)
        db.flush()
        db.add(
            CandidateSession(
                user_id=user.id,
                token_hash=digest_token("old-token"),
                expires_at=now - timedelta(seconds=60),
            )
        )
        db.add(
            CandidateEmailToken(
                user_id=user.id,
                token_hash=digest_token("old-email-token"),
                expires_at=now - timedelta(seconds=60),
            )
        )
        db.add(RateLimitBucket(key="x" * 64, hits=1, expires_at=now - timedelta(seconds=60)))
        db.commit()
    monkeypatch.setattr(cleanup, "get_session_factory", lambda: sessionmaker(bind=test_engine))
    result = cleanup.purge_all_expired()
    assert result["candidate_sessions"] == 1
    assert result["email_tokens"] == 1
    assert result["rate_limit_buckets"] == 1
    with Session(test_engine) as db:
        assert db.scalar(select(CandidateSession)) is None
        assert db.scalar(select(CandidateEmailToken)) is None
        assert db.scalar(select(RateLimitBucket)) is None
        assert db.scalar(select(CandidateUser)) is not None


def test_visitor_creation_rate_limit(client):
    from app.core.config import Settings, get_settings
    from app.main import app

    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql+psycopg://test:test@localhost/not_used",
        admin_api_key="test-key-not-for-production-12345678901234567890",
        visitor_creations_per_hour=2,
    )
    endpoint = "/api/v1/visitor/sessions"
    assert client.post(endpoint).status_code == 201
    assert client.post(endpoint).status_code == 201
    assert client.post(endpoint).status_code == 429
