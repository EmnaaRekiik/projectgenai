import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class CandidateRegister(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=12, max_length=128)

    @field_validator("display_name")
    @classmethod
    def clean_display_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Name cannot be blank")
        return value


class CandidateLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class CandidateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    display_name: str
    is_active: bool
    email_verified_at: datetime | None
    education_level: str | None
    interests: list[str]
    career_goal: str | None
    created_at: datetime


class CandidateTokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: CandidateOut


class CandidateProfilePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=2, max_length=120)
    education_level: str | None = Field(default=None, min_length=2, max_length=120)
    interests: list[str] | None = Field(default=None, max_length=15)
    career_goal: str | None = Field(default=None, min_length=2, max_length=500)

    @field_validator("interests")
    @classmethod
    def clean_interests(cls, interests):
        if interests is not None and any(not (2 <= len(x.strip()) <= 80) for x in interests):
            raise ValueError("Each interest must have between 2 and 80 characters")
        return [s.strip() for s in interests] if interests is not None else None


class CandidatePasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=12, max_length=128)


class VerifyEmail(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=32, max_length=200)
