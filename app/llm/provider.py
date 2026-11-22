"""SA-36: real HTTP LLM transport with native Ollama and OpenAI compatibility.

The native Ollama endpoint supports explicitly disabling thinking on models
that support the switch. No fake/simulated replies in production.
"""

from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.config import Settings


@dataclass(frozen=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class GeneratedReply:
    content: str
    model: str


class LLMUpstreamError(Exception):
    """Upstream model is unavailable or returned an invalid response."""


class LLMUpstreamTimeout(LLMUpstreamError):
    """Upstream model did not respond before the configured deadline."""


class OpenAICompatibleClient:
    def generate(self, messages: list[ChatMessage], settings: Settings) -> GeneratedReply:
        """Make an actual HTTP request; credentials and raw prompts are never logged."""
        if not settings.llm_base_url or not settings.llm_model:
            raise LLMUpstreamError("Model configuration missing")

        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        message_payload = [
            {"role": message.role, "content": message.content} for message in messages
        ]
        if settings.llm_provider == "ollama":
            # Accept the existing Docker .env base URL ending in /v1, but use
            # Ollama's native endpoint to support a non-thinking chat request.
            base = settings.llm_base_url.rstrip("/")
            if base.endswith("/v1"):
                base = base[:-3]
            url = base + "/api/chat"
            request = {
                "model": settings.llm_model,
                "messages": message_payload,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": settings.llm_max_output_tokens,
                },
            }
        else:
            request = {
                "model": settings.llm_model,
                "messages": message_payload,
                "temperature": 0.2,
                "max_tokens": settings.llm_max_output_tokens,
                "stream": False,
            }
            url = settings.llm_base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(
                timeout=settings.llm_timeout_seconds, follow_redirects=False
            ) as client:
                result = client.post(url, json=request, headers=headers)
                result.raise_for_status()
                data = result.json()
        except httpx.TimeoutException as exc:
            raise LLMUpstreamTimeout("Model request timed out") from exc
        except (httpx.HTTPError, ValueError) as exc:
            # Never include HTTP response body; it could contain prompts or keys.
            raise LLMUpstreamError("Model provider request failed") from exc

        try:
            if settings.llm_provider == "ollama":
                content = data["message"]["content"]
            else:
                content = data["choices"][0]["message"]["content"]
            model_name = data.get("model", settings.llm_model)
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LLMUpstreamError("Invalid model response format") from exc
        if not isinstance(content, str) or not content.strip():
            raise LLMUpstreamError("Model generated an empty response")
        if len(content) > settings.llm_max_response_chars:
            raise LLMUpstreamError("Model response exceeded safety length limit")
        if not isinstance(model_name, str):
            model_name = settings.llm_model
        return GeneratedReply(content=content.strip(), model=model_name)


def get_llm_client() -> OpenAICompatibleClient:
    return OpenAICompatibleClient()
