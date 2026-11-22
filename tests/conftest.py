"""API contract tests, run in SQLite for fast local feedback or PostgreSQL in CI.

Set TEST_DATABASE_URL to a migrated, disposable PostgreSQL database for real-dialect tests.
"""
import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, delete, event, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    ConversationMessage, Institution, Program, VisitorSession, StaffUser, StaffSession, StaffRole,
    ProgramSpecialization, ProgramCourse, ProgramAdmissionRule, ProgramTuition,
    CandidateUser, CandidateSession, CandidateEmailToken, RateLimitBucket,
    Appointment, EquivalenceRequest, InterviewResult, Preregistration,
    AcademicProfile, CandidateConversation, CandidateMessage,
    Document, DocumentChunk, DocumentVersion, IngestionJob,
)
from app.auth.tokens import digest_token
from app.auth.passwords import hash_password
from datetime import datetime, timedelta, timezone

TEST_KEY = "test-key-not-for-production-12345678901234567890"
TEST_TOKEN = "test-staff-token-not-for-production-1"
TEST_PASSWORD_HASH = hash_password("TestOnly-StrongPass_987654321")


@pytest.fixture(scope="session")
def test_engine():
    url = os.getenv("TEST_DATABASE_URL")
    if url:
        if not url.startswith("postgresql+psycopg://"):
            raise RuntimeError("TEST_DATABASE_URL must be PostgreSQL")
        engine = create_engine(url, pool_pre_ping=True)
        inspector = inspect(engine)
        assert inspector.has_table("institutions"), "Apply the Alembic migration before testing"
        assert inspector.has_table("programs"), "Apply the Alembic migration before testing"
        assert inspector.has_table("visitor_sessions"), "Apply the Alembic 0002 migration before testing"
        assert inspector.has_table("conversation_messages"), "Apply the Alembic 0002 migration before testing"
        assert "chat_request_id" in [c["name"] for c in inspector.get_columns("visitor_sessions")], "Apply Alembic 0003 before testing"
        assert inspector.has_table("staff_users"), "Apply Alembic 0004 before testing"
        assert inspector.has_table("staff_sessions"), "Apply Alembic 0004 before testing"
        for name in ("program_specializations", "program_courses", "program_admission_rules", "program_tuition",
                     "candidate_users", "candidate_sessions", "candidate_email_tokens", "rate_limit_buckets",
                     "preregistrations", "equivalence_requests", "appointments", "interview_results",
                     "academic_profiles", "candidate_conversations", "candidate_messages",
                     "documents", "document_versions", "document_chunks", "ingestion_jobs"):
            assert inspector.has_table(name), f"Apply Alembic 0005-0010 before testing: missing {name}"
    else:
        engine = create_engine(
            "sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(test_engine):
    with test_engine.begin() as conn:
        conn.execute(delete(IngestionJob))
        conn.execute(delete(DocumentChunk))
        conn.execute(delete(DocumentVersion))
        conn.execute(delete(Document))
        conn.execute(delete(CandidateMessage))
        conn.execute(delete(CandidateConversation))
        conn.execute(delete(AcademicProfile))
        conn.execute(delete(InterviewResult))
        conn.execute(delete(Appointment))
        conn.execute(delete(EquivalenceRequest))
        conn.execute(delete(Preregistration))
        conn.execute(delete(CandidateEmailToken))
        conn.execute(delete(CandidateSession))
        conn.execute(delete(CandidateUser))
        conn.execute(delete(RateLimitBucket))
        conn.execute(delete(ProgramCourse))
        conn.execute(delete(ProgramSpecialization))
        conn.execute(delete(ProgramAdmissionRule))
        conn.execute(delete(ProgramTuition))
        conn.execute(delete(StaffSession))
        conn.execute(delete(StaffUser))
        conn.execute(delete(ConversationMessage))
        conn.execute(delete(VisitorSession))
        conn.execute(delete(Program))
        conn.execute(delete(Institution))
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with factory() as session:
        admin = StaffUser(email="admin@example.org", display_name="Test Admin",
                          password_hash=TEST_PASSWORD_HASH, role=StaffRole.PLATFORM_ADMIN.value,
                          is_active=True, failed_login_count=0)
        session.add(admin)
        session.flush()
        session.add(StaffSession(user_id=admin.id, token_hash=digest_token(TEST_TOKEN),
                                 expires_at=datetime.now(timezone.utc) + timedelta(hours=12)))
        session.commit()

    def override_db():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql+psycopg://test:test@localhost/not_used",
        admin_api_key=TEST_KEY,
    )
    try:
        with TestClient(app) as http:
            yield http
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


@pytest.fixture
def institution(client, headers):
    response = client.post(
        "/api/v1/institutions", json={"code": "IIT", "name": "Institut International de Technologie"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def draft(client, headers, institution):
    response = client.post(
        "/api/v1/admin/programs",
        json={
            "institution_id": institution["id"],
            "code": "DEMO-LIC-1",
            "title": "Formation fictive pour tests uniquement",
            "level": "LICENCE",
            "duration_years": 3,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
