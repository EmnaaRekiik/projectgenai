"""T9: a visitor conversation is attached to a candidate account only with proof of ownership and consent."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import get_db
from app.main import app
from app.models import CandidateMessage, ConversationMessage, VisitorSession

PASSWORD = "Candidate_123456789!"
CLAIM = "/api/v1/candidates/me/conversations/claim"
CONVERSATIONS = "/api/v1/candidates/me/conversations"


def candidate(client, email="one@example.org"):
    assert (
        client.post(
            "/api/v1/candidates/register",
            json={"email": email, "display_name": "Candidat", "password": PASSWORD},
        ).status_code
        == 201
    )
    token = client.post(
        "/api/v1/candidates/login", json={"email": email, "password": PASSWORD}
    ).json()["access_token"]
    return {"Authorization": "Bearer " + token}


def visitor(client, messages=("Bonjour, je veux étudier l'informatique", "Quels sont les frais ?")):
    created = client.post("/api/v1/visitor/sessions").json()
    for text in messages:
        r = client.post(
            f"/api/v1/visitor/sessions/{created['id']}/messages",
            json={"content": text},
            headers={"X-Visitor-Token": created["token"]},
        )
        assert r.status_code == 201, r.text
    return created["id"], {"X-Visitor-Token": created["token"]}


def _db():
    return next(app.dependency_overrides[get_db]())


def add_assistant_reply(session_id, text="Voici les informations vérifiées."):
    db = _db()
    try:
        record = db.get(VisitorSession, uuid.UUID(session_id))
        db.add(
            ConversationMessage(
                session_id=record.id,
                role="assistant",
                sequence=record.next_message_sequence,
                content=text,
            )
        )
        record.next_message_sequence += 1
        db.commit()
    finally:
        db.close()


def claim(client, who, session_id, vheaders, consent=True):
    return client.post(
        CLAIM,
        json={"visitor_session_id": session_id, "consent": consent},
        headers={**who, **vheaders},
    )


def test_claim_copies_messages_in_order_and_keeps_visitor_data(client):
    who = candidate(client)
    session_id, vheaders = visitor(client)
    add_assistant_reply(session_id)
    response = claim(client, who, session_id, vheaders)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["message_count"] == 3 and body["already_claimed"] is False
    assert body["title"].startswith("Bonjour") and body["consent_given_at"] and body["claimed_at"]
    page = client.get(f"{CONVERSATIONS}/{body['id']}/messages", headers=who).json()
    assert [m["sequence"] for m in page["items"]] == [1, 2, 3]
    assert [m["role"] for m in page["items"]] == ["user", "user", "assistant"]
    assert page["items"][0]["content"] == "Bonjour, je veux étudier l'informatique"
    assert page["items"][0]["original_created_at"] is not None
    # visitor data is untouched (copy, not move)
    still = client.get(f"/api/v1/visitor/sessions/{session_id}/messages", headers=vheaders).json()
    assert still["total"] == 3


def test_consent_is_mandatory(client):
    who = candidate(client)
    session_id, vheaders = visitor(client)
    assert claim(client, who, session_id, vheaders, consent=False).status_code == 422
    r = client.post(CLAIM, json={"visitor_session_id": session_id}, headers={**who, **vheaders})
    assert r.status_code == 422
    assert client.get(CONVERSATIONS, headers=who).json() == []


def test_two_proofs_are_required(client):
    who = candidate(client)
    session_id, vheaders = visitor(client)
    body = {"visitor_session_id": session_id, "consent": True}
    assert client.post(CLAIM, json=body, headers=vheaders).status_code == 401  # no candidate login
    assert client.post(CLAIM, json=body, headers=who).status_code == 401  # no visitor token
    assert (
        client.post(CLAIM, json=body, headers={**who, "X-Visitor-Token": "wrong"}).status_code
        == 403
    )


def test_other_visitors_session_is_refused(client):
    who = candidate(client)
    session_id, _ = visitor(client)
    _, other_headers = visitor(client, messages=("autre",))
    assert claim(client, who, session_id, other_headers).status_code == 403
    assert client.get(CONVERSATIONS, headers=who).json() == []


def test_unknown_and_expired_sessions(client):
    who = candidate(client)
    unknown = "00000000-0000-4000-8000-000000000000"
    assert claim(client, who, unknown, {"X-Visitor-Token": "x"}).status_code == 404
    session_id, vheaders = visitor(client)
    db = _db()
    try:
        record = db.get(VisitorSession, uuid.UUID(session_id))
        record.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    assert claim(client, who, session_id, vheaders).status_code == 410
    assert client.get(CONVERSATIONS, headers=who).json() == []


def test_double_click_is_idempotent_and_does_not_duplicate(client):
    who = candidate(client)
    session_id, vheaders = visitor(client)
    first = claim(client, who, session_id, vheaders)
    second = claim(client, who, session_id, vheaders)
    assert first.status_code == 201 and second.status_code == 200
    assert second.json()["id"] == first.json()["id"] and second.json()["already_claimed"] is True
    assert second.json()["message_count"] == 2
    assert len(client.get(CONVERSATIONS, headers=who).json()) == 1


def test_session_cannot_be_claimed_by_another_account(client):
    first = candidate(client, "one@example.org")
    second = candidate(client, "two@example.org")
    session_id, vheaders = visitor(client)
    assert claim(client, first, session_id, vheaders).status_code == 201
    assert claim(client, second, session_id, vheaders).status_code == 409
    assert client.get(CONVERSATIONS, headers=second).json() == []


def test_empty_session_is_refused(client):
    who = candidate(client)
    session_id, vheaders = visitor(client, messages=())
    assert claim(client, who, session_id, vheaders).status_code == 409


def test_chat_in_progress_blocks_claim(client):
    who = candidate(client)
    session_id, vheaders = visitor(client)
    db = _db()
    try:
        record = db.get(VisitorSession, uuid.UUID(session_id))
        record.chat_request_id = uuid.uuid4()
        record.chat_lease_until = datetime.now(timezone.utc) + timedelta(minutes=2)
        db.commit()
    finally:
        db.close()
    assert claim(client, who, session_id, vheaders).status_code == 409
    assert client.get(CONVERSATIONS, headers=who).json() == []


def test_claim_survives_visitor_purge_and_repeat_still_succeeds(client):
    who = candidate(client)
    session_id, vheaders = visitor(client)
    created = claim(client, who, session_id, vheaders).json()
    assert (
        client.delete(f"/api/v1/visitor/sessions/{session_id}", headers=vheaders).status_code == 204
    )
    repeat = claim(client, who, session_id, vheaders)
    assert repeat.status_code == 200 and repeat.json()["id"] == created["id"]
    assert client.get(f"{CONVERSATIONS}/{created['id']}/messages", headers=who).json()["total"] == 2


def test_conversations_are_private_and_deletable(client, headers):
    first = candidate(client, "one@example.org")
    second = candidate(client, "two@example.org")
    session_id, vheaders = visitor(client)
    conversation = claim(client, first, session_id, vheaders).json()
    url = f"{CONVERSATIONS}/{conversation['id']}"
    assert client.get(url, headers=second).status_code == 404
    assert client.get(url + "/messages", headers=second).status_code == 404
    assert client.delete(url, headers=second).status_code == 404
    assert (
        client.get(CONVERSATIONS, headers=headers).status_code == 401
    )  # staff token is not a candidate token
    assert client.get(url, headers=first).json()["message_count"] == 2
    assert client.delete(url, headers=first).status_code == 204
    assert client.get(url, headers=first).status_code == 404
    db = _db()
    try:
        assert (
            db.scalars(select(CandidateMessage)).all() == []
        )  # messages removed with the conversation
    finally:
        db.close()


def test_pagination_of_candidate_messages(client):
    who = candidate(client)
    session_id, vheaders = visitor(client, messages=tuple(f"message {i}" for i in range(1, 6)))
    cid = claim(client, who, session_id, vheaders).json()["id"]
    page = client.get(f"{CONVERSATIONS}/{cid}/messages?limit=2&offset=2", headers=who).json()
    assert page["total"] == 5 and [m["sequence"] for m in page["items"]] == [3, 4]
    assert client.get(f"{CONVERSATIONS}/{cid}/messages?limit=0", headers=who).status_code == 422


def test_claim_attempts_are_rate_limited(client):
    who = candidate(client)
    session_id, _ = visitor(client)
    codes = [
        claim(client, who, session_id, {"X-Visitor-Token": "wrong"}).status_code for _ in range(31)
    ]
    assert codes[:30] == [403] * 30
    assert codes[30] == 429
