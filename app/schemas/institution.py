import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InstitutionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z][A-Z0-9_-]*$")
    name: str = Field(min_length=2, max_length=160)

    @field_validator("name")
    @classmethod
    def trim_name(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 2:
            raise ValueError("Name must contain at least 2 non-space characters")
        return cleaned


class InstitutionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    created_at: datetime
