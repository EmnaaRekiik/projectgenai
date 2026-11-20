import httpx
import pytest

from app.core.config import Settings
from app.llm import provider
from app.llm.context import SYSTEM_INSTRUCTIONS
from app.llm.provider import ChatMessage, LLMUpstreamError, OpenAICompatibleClient


def setting(**kwargs):
    return Settings(
        database_url="postgresql+psycopg://a:b@localhost/db",
        llm_base_url="https://llm.example.test/v1",
        llm_model="example-model",
        llm_api_key="some-key",
        **kwargs,
    )


def patched_client(monkeypatch, callback):
    original_client = httpx.Client
    monkeypatch.setattr(provider.httpx, "Client", lambda **kw: original_client(transport=httpx.MockTransport(callback), **kw))


def test_provider_sends_real_openai_compatible_request(monkeypatch):
    def respond(request):
        assert str(request.url) == "https://llm.example.test/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer some-key"
        import json
        payload = json.loads(request.content)
        assert payload["model"] == "example-model"
        assert payload["messages"][-1] == {"role": "user", "content": "salem"}
        return httpx.Response(200, json={"choices": [{"message": {"content": " Ahla! "}}], "model": "example-model"})
    patched_client(monkeypatch, respond)
    result = OpenAICompatibleClient().generate([ChatMessage(role="user", content="salem")], setting())
    assert result.content == "Ahla!"


def test_provider_rejects_invalid_json_shape_and_does_not_expose_body(monkeypatch):
    patched_client(monkeypatch, lambda r: httpx.Response(401, text="SECRET_PROVIDER_RESPONSE"))
    with pytest.raises(LLMUpstreamError) as error:
        OpenAICompatibleClient().generate([ChatMessage(role="user", content="hi")], setting())
    assert "SECRET_PROVIDER_RESPONSE" not in str(error.value)


def test_provider_rejects_malformed_success(monkeypatch):
    patched_client(monkeypatch, lambda r: httpx.Response(200, json={"choices": []}))
    with pytest.raises(LLMUpstreamError):
        OpenAICompatibleClient().generate([ChatMessage(role="user", content="hi")], setting())


def test_llm_url_blocks_remote_cleartext_http():
    with pytest.raises(ValueError):
        Settings(database_url="postgresql+psycopg://a:b@localhost/db", llm_base_url="http://llm.example.test/v1")


def test_system_prompt_requires_verified_sources():
    assert "données vérifiées" in SYSTEM_INSTRUCTIONS.lower()


def test_native_ollama_disables_thinking_and_returns_only_content(monkeypatch):
    import json
    from app.llm.provider import ChatMessage

    def respond(request):
        assert str(request.url) == "http://host.docker.internal:11434/api/chat"
        payload = json.loads(request.content)
        assert payload["model"] == "qwen3.5:4b"
        assert payload["stream"] is False
        assert payload["think"] is False
        assert payload["options"]["num_predict"] == 256
        assert payload["messages"][-1]["content"] == "salem"
        return httpx.Response(200, json={
            "model": "qwen3.5:4b",
            "message": {"role": "assistant", "thinking": "private reasoning", "content": "Marhba!"},
        })

    patched_client(monkeypatch, respond)
    cfg = Settings(
        database_url="postgresql+psycopg://a:b@localhost/db",
        llm_provider="ollama",
        llm_base_url="http://host.docker.internal:11434/v1",
        llm_model="qwen3.5:4b",
        llm_max_output_tokens=256,
        llm_timeout_seconds=240,
    )
    result = OpenAICompatibleClient().generate([ChatMessage(role="user", content="salem")], cfg)
    assert result.content == "Marhba!"
    assert "private" not in result.content


def test_native_ollama_rejects_empty_content_even_with_thinking(monkeypatch):
    from app.llm.provider import ChatMessage
    patched_client(monkeypatch, lambda r: httpx.Response(200, json={
        "model": "qwen3.5:4b", "message": {"content": "", "thinking": "only thinking"}
    }))
    cfg = Settings(
        database_url="postgresql+psycopg://a:b@localhost/db",
        llm_provider="ollama", llm_base_url="http://host.docker.internal:11434/v1",
        llm_model="qwen3.5:4b",
    )
    with pytest.raises(LLMUpstreamError, match="empty response"):
        OpenAICompatibleClient().generate([ChatMessage(role="user", content="hi")], cfg)


def test_extended_timeout_is_validated():
    from pydantic import ValidationError
    assert setting(llm_timeout_seconds=240).llm_timeout_seconds == 240
    with pytest.raises(ValidationError):
        setting(llm_timeout_seconds=301)
