"""Contract/security/expiry/privacy coverage for SA-25 and SA-26."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

import app.db.purge_expired as maintenance
from app.models import ConversationMessage, VisitorSession

BASE = "/api/v1/visitor/sessions"


def new_session(client):
    r = client.post(BASE)
    assert r.status_code == 201, r.text
    return r.json()


def auth(created):
    return {"X-Visitor-Token": created["token"]}


def add(client, created, text):
    return client.post(
        f"{BASE}/{created['id']}/messages", headers=auth(created), json={"content": text}
    )


def test_create_session_returns_opaque_one_time_token(client, test_engine):
    created = new_session(client)
    assert uuid.UUID(created["id"])
    assert len(created["token"]) >= 40
    assert "token" not in client.get(f"{BASE}/{created['id']}", headers=auth(created)).json()
    with test_engine.connect() as conn:
        row = conn.execute(
            select(VisitorSession).where(VisitorSession.id == uuid.UUID(created["id"]))
        )
        # ORM select needs Session: check only through normal connection raw row mapping.
        stored = row.fetchone()
    assert stored is not None
    # Hash is stored, plaintext never is.
    assert hashlib.sha256(created["token"].encode()).hexdigest() in tuple(str(x) for x in stored)
    assert created["token"] not in str(stored)


def test_session_token_is_random_per_visitor(client):
    first, second = new_session(client), new_session(client)
    assert first["id"] != second["id"]
    assert first["token"] != second["token"]


def test_missing_wrong_and_cross_session_tokens_denied(client):
    first, second = new_session(client), new_session(client)
    url = f"{BASE}/{first['id']}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"X-Visitor-Token": "fake"}).status_code == 404
    assert client.get(url, headers=auth(second)).status_code == 404
    assert (
        client.post(url + "/messages", json={"content": "secret"}, headers=auth(second)).status_code
        == 404
    )
    assert client.get(url + "/context", headers=auth(second)).status_code == 404
    assert client.get(url + "/messages", headers=auth(second)).status_code == 404
    assert client.delete(url, headers=auth(second)).status_code == 404


def test_multi_turn_memory_stored_in_order(client):
    created = new_session(client)
    for number, text in enumerate(["Salem", "Nheb na9ra informatique", "Fasserli el licence"], 1):
        r = add(client, created, text)
        assert r.status_code == 201, r.text
        assert r.json()["sequence"] == number
        assert r.json()["role"] == "user"
    messages = client.get(f"{BASE}/{created['id']}/messages", headers=auth(created)).json()
    assert messages["total"] == 3
    assert [m["sequence"] for m in messages["items"]] == [1, 2, 3]
    assert [m["content"] for m in messages["items"]] == [
        "Salem",
        "Nheb na9ra informatique",
        "Fasserli el licence",
    ]


def test_memory_isolation(client):
    first, second = new_session(client), new_session(client)
    assert add(client, first, "private academic preferences").status_code == 201
    assert add(client, second, "other candidate preferences").status_code == 201
    context_a = client.get(f"{BASE}/{first['id']}/context", headers=auth(first)).json()
    context_b = client.get(f"{BASE}/{second['id']}/context", headers=auth(second)).json()
    assert [m["content"] for m in context_a["messages"]] == ["private academic preferences"]
    assert [m["content"] for m in context_b["messages"]] == ["other candidate preferences"]


def test_last_messages_context_window_and_truncation(client):
    created = new_session(client)
    for n in range(7):
        assert add(client, created, f"question {n}").status_code == 201
    result = client.get(f"{BASE}/{created['id']}/context?limit=3", headers=auth(created))
    assert result.status_code == 200
    assert result.json()["truncated"] is True
    assert [item["content"] for item in result.json()["messages"]] == [
        "question 4",
        "question 5",
        "question 6",
    ]
    all_context = client.get(
        f"{BASE}/{created['id']}/context?limit=20", headers=auth(created)
    ).json()
    assert all_context["truncated"] is False


def test_paginated_messages(client):
    created = new_session(client)
    for i in range(5):
        add(client, created, f"message {i}")
    result = client.get(f"{BASE}/{created['id']}/messages?limit=2&offset=2", headers=auth(created))
    assert result.status_code == 200
    body = result.json()
    assert body["total"] == 5 and body["offset"] == 2
    assert [item["content"] for item in body["items"]] == ["message 2", "message 3"]
    assert (
        client.get(f"{BASE}/{created['id']}/messages?limit=0", headers=auth(created)).status_code
        == 422
    )
    assert (
        client.get(f"{BASE}/{created['id']}/context?limit=31", headers=auth(created)).status_code
        == 422
    )


def test_validation_and_no_client_assistant_impersonation(client):
    created = new_session(client)
    for payload in (
        {"content": "   "},
        {"content": ""},
        {"content": "a" * 4001},
        {"content": "hello", "role": "assistant"},
    ):
        r = client.post(f"{BASE}/{created['id']}/messages", json=payload, headers=auth(created))
        assert r.status_code == 422, (payload.keys(), r.text)
    r = add(client, created, "   a real question   ")
    assert r.status_code == 201
    assert r.json()["content"] == "a real question"


def test_max_message_count_enforced(client):
    from app.core.config import get_settings
    from app.main import app

    # The test fixture overrides get_settings, so also replace its override.
    original_override = app.dependency_overrides[get_settings]
    configured = original_override()
    configured.visitor_max_messages = 2
    app.dependency_overrides[get_settings] = lambda: configured
    created = new_session(client)
    assert add(client, created, "one").status_code == 201
    assert add(client, created, "two").status_code == 201
    assert add(client, created, "three").status_code == 409


def test_session_expiration(client, test_engine):
    created = new_session(client)
    with Session(test_engine) as db:
        record = db.get(VisitorSession, uuid.UUID(created["id"]))
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get(f"{BASE}/{created['id']}", headers=auth(created)).status_code == 410
    assert add(client, created, "past expiry").status_code == 410


def test_delete_session_cascades_history(client, test_engine):
    created = new_session(client)
    assert add(client, created, "delete me").status_code == 201
    url = f"{BASE}/{created['id']}"
    assert client.delete(url, headers=auth(created)).status_code == 204
    assert client.get(url, headers=auth(created)).status_code == 404
    with Session(test_engine) as db:
        count = db.query(ConversationMessage).filter_by(session_id=uuid.UUID(created["id"])).count()
    assert count == 0


def test_swagger_exposes_visitor_auth_scheme(client):
    spec = client.get("/openapi.json").json()
    schemes = spec["components"]["securitySchemes"]
    assert schemes["BootstrapKey"]["name"] == "X-Admin-Key"
    assert schemes["StaffBearer"]["scheme"] == "bearer"
    assert schemes["VisitorSessionToken"]["name"] == "X-Visitor-Token"
    endpoint = spec["paths"]["/api/v1/visitor/sessions/{session_id}/messages"]["post"]
    assert endpoint.get("security")


def test_retention_job_purges_expired_messages(client, test_engine, monkeypatch):

    # Mimic PostgreSQL's ON DELETE CASCADE in the SQLite-only fast-test double.
    with test_engine.connect() as conn:
        conn.exec_driver_sql("PRAGMA foreign_keys=ON")
    created = new_session(client)
    assert add(client, created, "temporary context").status_code == 201
    with Session(test_engine) as db:
        record = db.get(VisitorSession, uuid.UUID(created["id"]))
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=2)
        db.commit()
    monkeypatch.setattr(maintenance, "get_session_factory", lambda: sessionmaker(bind=test_engine))
    assert maintenance.purge_expired() == 1
    with Session(test_engine) as db:
        assert db.get(VisitorSession, uuid.UUID(created["id"])) is None
        assert (
            db.query(ConversationMessage).filter_by(session_id=uuid.UUID(created["id"])).count()
            == 0
        )
