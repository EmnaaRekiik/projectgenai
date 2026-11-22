"""Ephemeral anonymous visitor sessions and conversation history.

Session tokens are returned once and never written to the database in plaintext.
The application does not record IP addresses or user agents in this module.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class VisitorSession(Base):
    __tablename__ = "visitor_sessions"
    __table_args__ = (
        CheckConstraint("next_message_sequence >= 1", name="ck_visitor_next_sequence"),
        Index("ix_visitor_sessions_expires_at", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_message_sequence: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Database lease: avoids overlapping model calls writing out-of-order turns.
    chat_request_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    chat_lease_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    messages: Mapped[list["ConversationMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ConversationMessage.sequence",
    )


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_conversation_session_sequence"),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_conversation_message_role"),
        CheckConstraint("sequence >= 1", name="ck_conversation_sequence_positive"),
        Index("ix_conversation_messages_session_id_sequence", "session_id", "sequence"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("visitor_sessions.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    session: Mapped["VisitorSession"] = relationship(back_populates="messages")
