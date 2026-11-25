"""Contracts for candidate-owned conversations (T9: claim a visitor conversation after login)."""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ClaimRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visitor_session_id: uuid.UUID = Field(
        description="Visitor session whose conversation is attached to the account"
    )
    # Literal[True]: omitted, false or any other value is rejected with 422. Consent must be explicit.
    consent: Literal[True] = Field(
        description="Must be true: the candidate agrees to keep this conversation in their profile"
    )


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str | None
    status: Literal["ACTIVE", "ARCHIVED"]
    consent_given_at: datetime | None
    claimed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ClaimOut(ConversationOut):
    already_claimed: bool = Field(
        default=False,
        description="True when the same candidate repeated an earlier claim (idempotent)",
    )


class ConversationMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    original_created_at: datetime | None
    created_at: datetime


class ConversationMessagePage(BaseModel):
    items: list[ConversationMessageOut]
    total: int
    limit: int
    offset: int
