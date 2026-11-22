"""Validated PostgreSQL runtime configuration; no SQLite fallback."""

from functools import lru_cache
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_file_encoding="utf-8")

    # Either an explicit DSN (e.g., local Python) or separate Docker credentials.
    database_url: str | None = None
    db_host: str | None = None
    db_port: int = 5432
    db_user: str | None = None
    db_password: str | None = None
    db_name: str | None = None
    admin_api_key: str | None = None
    staff_session_ttl_hours: int = Field(default=12, ge=1, le=72)
    candidate_session_ttl_hours: int = Field(default=12, ge=1, le=72)
    visitor_creations_per_hour: int = Field(default=300, ge=1, le=10000)
    candidate_registrations_per_hour: int = Field(default=10, ge=1, le=1000)
    candidate_login_attempts_per_hour: int = Field(default=60, ge=1, le=10000)
    retention_interval_seconds: int = Field(default=3600, ge=60, le=86400)
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_from: str | None = None
    smtp_username: str | None = None
    smtp_password: str | None = None
    visitor_session_ttl_hours: int = Field(default=24, ge=1, le=168)
    visitor_max_messages: int = Field(default=200, ge=1, le=1000)
    llm_base_url: str | None = None
    llm_provider: Literal["openai", "ollama"] = "openai"
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_timeout_seconds: int = Field(default=45, ge=5, le=300)
    llm_max_output_tokens: int = Field(default=500, ge=64, le=1500)
    llm_context_messages: int = Field(default=12, ge=1, le=30)
    llm_max_response_chars: int = Field(default=8000, ge=500, le=16000)

    @field_validator("database_url")
    @classmethod
    def require_postgres(cls, value: str | None) -> str | None:
        if value is not None and not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_URL must use postgresql+psycopg:// (SQLite not allowed)")
        return value

    @field_validator("admin_api_key")
    @classmethod
    def require_strong_api_key(cls, value: str | None) -> str | None:
        if value is not None and value.startswith("REPLACE_WITH_"):
            raise ValueError("ADMIN_API_KEY placeholder must be replaced")
        if value is not None and len(value) < 32:
            raise ValueError("ADMIN_API_KEY must have at least 32 characters")
        return value

    @field_validator("db_password")
    @classmethod
    def reject_password_placeholder(cls, value: str | None) -> str | None:
        if value is not None and value.startswith("REPLACE_WITH_"):
            raise ValueError("DB_PASSWORD placeholder must be replaced")
        return value

    @field_validator("llm_base_url")
    @classmethod
    def secure_llm_url(cls, value: str | None) -> str | None:
        if not value:
            return None
        parsed = urlparse(value)
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("LLM_BASE_URL must not contain secrets, query or fragments")
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("LLM_BASE_URL must be an HTTP(S) URL")
        if parsed.scheme == "http" and parsed.hostname not in {
            "localhost",
            "127.0.0.1",
            "host.docker.internal",
            "ollama",
            "::1",
        }:
            raise ValueError("Remote LLM endpoints must use HTTPS")
        return value.rstrip("/")

    @field_validator("llm_model")
    @classmethod
    def nonempty_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def require_connection_settings(self) -> "Settings":
        if self.database_url is None and not all(
            (self.db_host, self.db_user, self.db_password, self.db_name)
        ):
            raise ValueError("Supply DATABASE_URL or DB_HOST, DB_USER, DB_PASSWORD and DB_NAME")
        return self

    @property
    def sqlalchemy_url(self) -> URL:
        if self.database_url:
            return make_url(self.database_url)
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.db_user,
            password=self.db_password,  # URL.create escapes special characters safely
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
