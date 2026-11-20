"""SA-36/SA-37: live-model integration contract tests with injected fake transport.

The deterministic stub is test-only. The production provider always calls an
actual configured OpenAI-compatible HTTP endpoint.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.provider import (
    GeneratedReply, LLMUpstreamError, LLMUpstreamTimeout, get_llm_client,
)
from app.main import app
from app.models.visitor import VisitorSession

BASE = "/api/v1/visitor/sessions"


class StubLLM:
    def __init__(self, answer="Marhba! Chnowa t7eb ta9ra?"):
        self.answer = answer
        self.calls = []
        self.error = None

    def generate(self, messages, settings):
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return GeneratedReply(content=self.answer, model="stub-in-tests-only")


def connected(client, fake=None):
    client_app = app
    base_settings = client_app.dependency_overrides[get_settings]()
    base_settings.llm_base_url = "http://127.0.0.1:11434/v1"
    base_settings.llm_model = "test-model"
    client_app.dependency_overrides[get_settings] = lambda: base_settings
    fake = fake or StubLLM()
    client_app.dependency_overrides[get_llm_client] = lambda: fake
    return fake


def new_session(client):
    response = client.post(BASE)
    assert response.status_code == 201, response.text
    return response.json()


def chat(client, session, content):
    return client.post(
        f"{BASE}/{session['id']}/chat",
        headers={"X-Visitor-Token": session["token"]},
        json={"content": content},
    )


def history(client, session):
    return client.get(
        f"{BASE}/{session['id']}/messages",
        headers={"X-Visitor-Token": session["token"]},
    ).json()["items"]


def test_successful_chat_writes_both_messages_and_reuses_memory(client):
    fake = connected(client)
    session = new_session(client)
    first = chat(client, session, "Salem, nheb na9ra info")
    assert first.status_code == 201, first.text
    assert first.json()["user_message"]["sequence"] == 1
    assert first.json()["assistant_message"]["sequence"] == 2
    assert first.json()["model"] == "stub-in-tests-only"
    assert first.json()["catalogue_sources"] == []
    assert "Aucun programme" in fake.calls[0][0].content
    assert fake.calls[0][-1].content == "Salem, nheb na9ra info"

    followup = chat(client, session, "Tnajem tfasserli akther?")
    assert followup.status_code == 201, followup.text
    assert followup.json()["user_message"]["sequence"] == 3
    assert followup.json()["assistant_message"]["sequence"] == 4
    assert [(msg.role, msg.content) for msg in fake.calls[1][1:]] == [
        ("user", "Salem, nheb na9ra info"),
        ("assistant", "Marhba! Chnowa t7eb ta9ra?"),
        ("user", "Tnajem tfasserli akther?"),
    ]
    assert [m["role"] for m in history(client, session)] == [
        "user", "assistant", "user", "assistant"
    ]


def test_unconfigured_model_does_not_store_message(client):
    session = new_session(client)
    result = chat(client, session, "Hi")
    assert result.status_code == 503
    assert history(client, session) == []


def test_only_owner_can_chat(client):
    connected(client)
    mine, other = new_session(client), new_session(client)
    result = client.post(
        f"{BASE}/{mine['id']}/chat",
        headers={"X-Visitor-Token": other["token"]}, json={"content": "secret"}
    )
    assert result.status_code == 404
    assert history(client, mine) == []


def test_failed_model_call_rolls_back_turn_and_releases_lease(client, test_engine):
    fake = connected(client)
    session = new_session(client)
    fake.error = LLMUpstreamError("do not print internal provider secret")
    result = chat(client, session, "something personal")
    assert result.status_code == 502
    assert "secret" not in result.text
    assert history(client, session) == []
    fake.error = None
    assert chat(client, session, "retry").status_code == 201
    assert [m["sequence"] for m in history(client, session)] == [1, 2]


def test_model_timeout_rolls_back_turn(client):
    fake = connected(client)
    fake.error = LLMUpstreamTimeout("timeout")
    session = new_session(client)
    assert chat(client, session, "request").status_code == 504
    assert history(client, session) == []


def test_inflight_lease_blocks_overlapping_chat_and_raw_messages(client, test_engine):
    connected(client)
    session = new_session(client)
    with Session(test_engine) as db:
        record = db.get(VisitorSession, uuid.UUID(session["id"]))
        record.chat_request_id = uuid.uuid4()
        record.chat_lease_until = datetime.now(timezone.utc) + timedelta(seconds=60)
        db.commit()
    assert chat(client, session, "overlap").status_code == 409
    r = client.post(
        f"{BASE}/{session['id']}/messages",
        headers={"X-Visitor-Token": session["token"]}, json={"content": "overlap"}
    )
    assert r.status_code == 409
    assert history(client, session) == []


def test_expired_lease_can_be_recovered(client, test_engine):
    connected(client)
    session = new_session(client)
    with Session(test_engine) as db:
        record = db.get(VisitorSession, uuid.UUID(session["id"]))
        record.chat_request_id = uuid.uuid4()
        record.chat_lease_until = datetime.now(timezone.utc) - timedelta(seconds=5)
        db.commit()
    assert chat(client, session, "after recovery").status_code == 201
    assert len(history(client, session)) == 2


def test_two_slots_required_for_chat(client):
    connected(client)
    settings = app.dependency_overrides[get_settings]()
    settings.visitor_max_messages = 1
    session = new_session(client)
    assert chat(client, session, "cannot fit both turns").status_code == 409
    assert history(client, session) == []


def test_bad_model_content_cannot_pollute_history(client):
    fake = connected(client, StubLLM(" "))
    session = new_session(client)
    assert chat(client, session, "first").status_code == 502
    assert history(client, session) == []
    fake.answer = "hello"
    assert chat(client, session, "again").status_code == 201


def test_snapshot_exposes_chat_endpoint_and_same_visitor_security(client):
    path = "/api/v1/visitor/sessions/{session_id}/chat"
    spec = client.get("/openapi.json").json()
    assert spec["paths"][path]["post"]["security"] == [{"VisitorSessionToken": []}]


def test_published_catalogue_is_in_prompt_but_draft_is_not(client, headers, institution):
    fake = connected(client)
    draft = client.post(
        "/api/v1/admin/programs", headers=headers,
        json={"institution_id": institution["id"], "code": "DRAFT-TEST", "title": "Fake secret programme", "level": "LICENCE"}
    )
    assert draft.status_code == 201, draft.text
    pub = client.post(
        "/api/v1/admin/programs", headers=headers,
        json={"institution_id": institution["id"], "code": "PUBLISHED-TEST", "title": "Verified sample programme", "level": "ENGINEERING", "official_source_url": "https://example.org/verified", "verified_at": "2026-11-20T00:00:00Z"}
    )
    assert pub.status_code == 201, pub.text
    publish = client.patch(f"/api/v1/admin/programs/{pub.json()['id']}", json={"status": "PUBLISHED", "verified_at": "2026-11-20T00:00:00Z"}, headers=headers)
    assert publish.status_code == 200, publish.text
    session = new_session(client)
    response = chat(client, session, "Quelle formation ?")
    assert response.status_code == 201, response.text
    assert "Verified sample programme" in fake.calls[0][0].content
    assert "Fake secret programme" not in fake.calls[0][0].content
    assert response.json()["catalogue_sources"][0]["url"] == "https://example.org/verified"


def test_real_http_transport_is_wired_to_actual_conversation_history(client, monkeypatch):
    """One integrated TestClient -> DB -> HTTP transport -> DB flow (mock HTTP, not fake model)."""
    import httpx
    from app.llm import provider as model_provider

    connected(client)
    app.dependency_overrides.pop(get_llm_client)  # production provider path
    calls = []
    original_client = httpx.Client

    def respond(request):
        import json
        payload = json.loads(request.content)
        calls.append(payload["messages"])
        return httpx.Response(200, json={
            "model": "test-transport-model", "choices": [{"message": {"content": "Réponse générée depuis HTTP de test"}}]
        })

    monkeypatch.setattr(model_provider.httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw))
    session = new_session(client)
    assert chat(client, session, "question initiale").status_code == 201
    assert chat(client, session, "deuxième question").status_code == 201
    assert calls[1][-3:] == [
        {"role": "user", "content": "question initiale"},
        {"role": "assistant", "content": "Réponse générée depuis HTTP de test"},
        {"role": "user", "content": "deuxième question"},
    ]
    assert len(history(client, session)) == 4


def test_native_ollama_transport_preserves_two_turn_history(client, monkeypatch):
    """FastAPI -> PostgreSQL(test DB) -> Ollama native HTTP mock -> PostgreSQL."""
    import httpx
    import json
    from app.llm import provider as model_provider

    connected(client)
    settings = app.dependency_overrides[get_settings]()
    settings.llm_provider = "ollama"
    settings.llm_model = "qwen3.5:4b"
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides.pop(get_llm_client)
    calls = []
    original_client = httpx.Client

    def respond(request):
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        payload = json.loads(request.content)
        assert payload["think"] is False
        assert payload["stream"] is False
        calls.append(payload["messages"])
        return httpx.Response(200, json={
            "model": "qwen3.5:4b",
            "message": {"role": "assistant", "content": "Ahla, na3ref!", "thinking": "not retained"},
        })

    monkeypatch.setattr(
        model_provider.httpx, "Client",
        lambda **kw: original_client(transport=httpx.MockTransport(respond), **kw),
    )
    session = new_session(client)
    assert chat(client, session, "nheb informatique").status_code == 201
    assert chat(client, session, "tfakker chnouwa nheb?").status_code == 201
    assert calls[1][-3:] == [
        {"role": "user", "content": "nheb informatique"},
        {"role": "assistant", "content": "Ahla, na3ref!"},
        {"role": "user", "content": "tfakker chnouwa nheb?"},
    ]
    assert len(history(client, session)) == 4
    assert all("not retained" not in item["content"] for item in history(client, session))
