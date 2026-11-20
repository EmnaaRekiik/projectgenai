import uuid
from datetime import datetime
from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class Level(str, Enum):
    LICENCE = "LICENCE"
    PREPARATORY = "PREPARATORY"
    ENGINEERING = "ENGINEERING"
    OTHER = "OTHER"


class ProgramStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class ProgramCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    institution_id: uuid.UUID
    code: str = Field(min_length=2, max_length=50, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    title: str = Field(min_length=2, max_length=180)
    level: Level
    duration_years: int | None = Field(default=None, ge=1, le=10)
    description: str | None = Field(default=None, max_length=5000)
    official_source_url: HttpUrl | None = Field(default=None, max_length=500)
    verified_at: datetime | None = None

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must contain at least 2 non-space characters")
        return cleaned


class ProgramPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=2, max_length=180)
    level: Level | None = None
    duration_years: int | None = Field(default=None, ge=1, le=10)
    description: str | None = Field(default=None, max_length=5000)
    official_source_url: HttpUrl | None = Field(default=None, max_length=500)
    verified_at: datetime | None = None
    status: ProgramStatus | None = None

    @field_validator("title")
    @classmethod
    def trim_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Title must contain at least 2 non-space characters")
        return cleaned


class ProgramOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    institution_id: uuid.UUID
    code: str
    title: str
    level: Level
    duration_years: int | None
    description: str | None
    official_source_url: str | None
    verified_at: datetime | None
    status: ProgramStatus
    created_at: datetime
    updated_at: datetime


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int
