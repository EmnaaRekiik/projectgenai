"""Public contracts for anonymous visitor sessions and messages."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VisitorSessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    expires_at: datetime
    last_activity_at: datetime


class VisitorSessionCreated(VisitorSessionOut):
    # A bearer secret, sent only in this response. Do not persist on frontend logs.
    token: str = Field(description="One-time secret; send via X-Visitor-Token for later requests")


class UserMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def no_blank_messages(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Message cannot be blank")
        return stripped


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sequence: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class MessagePage(BaseModel):
    items: list[MessageOut]
    total: int
    limit: int
    offset: int


class ContextMessage(BaseModel):
    sequence: int
    role: Literal["user", "assistant"]
    content: str


class ConversationContext(BaseModel):
    session_id: uuid.UUID
    messages: list[ContextMessage]
    truncated: bool


class ModelReply(BaseModel):
    session_id: uuid.UUID
    user_message: MessageOut
    assistant_message: MessageOut
    model: str
    truncated_history: bool
    catalogue_sources: list[dict[str, str]] = Field(
        default_factory=list,
        description="Verified catalogue references supplied to the model; not proof the reply cites them",
    )
