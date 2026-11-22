"""Candidate-owned academic profile and conversations kept after a visitor creates an account.

Visitor chat data (visitor_sessions / conversation_messages) is unchanged and still expires.
A conversation becomes candidate-owned only when the candidate explicitly consents and proves
ownership of the visitor session (see docs/DONNEES_T4_T5.md). Messages are then copied here.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

LANGUAGES = ("fr", "derja", "arabizi", "mixed")
PROFILE_SOURCES = ("CANDIDATE", "AGENT", "STAFF")
CONVERSATION_STATUSES = ("ACTIVE", "ARCHIVED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class AcademicProfile(Base):
    __tablename__ = "academic_profiles"
    __table_args__ = (
        UniqueConstraint("candidate_id", name="uq_academic_profile_candidate"),
        CheckConstraint(
            "average_grade IS NULL OR (average_grade >= 0 AND average_grade <= 20)",
            name="ck_profile_grade",
        ),
        CheckConstraint(
            "bac_year IS NULL OR (bac_year >= 1990 AND bac_year <= 2100)",
            name="ck_profile_bac_year",
        ),
        CheckConstraint(
            "preferred_language IS NULL OR " + _in("preferred_language", LANGUAGES),
            name="ck_profile_language",
        ),
        CheckConstraint(_in("source", PROFILE_SOURCES), name="ck_profile_source"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False
    )
    bac_series: Mapped[str | None] = mapped_column(String(60))
    bac_year: Mapped[int | None] = mapped_column(Integer)
    average_grade: Mapped[float | None] = mapped_column(Numeric(5, 2))  # Tunisian scale, 0-20
    favorite_subjects: Mapped[str | None] = mapped_column(
        Text
    )  # JSON array, serialized only by schema
    interests: Mapped[str | None] = mapped_column(Text)  # JSON array
    career_goal: Mapped[str | None] = mapped_column(String(500))
    constraints_note: Mapped[str | None] = mapped_column(Text)  # budget, location, schedule
    preferred_language: Mapped[str | None] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="CANDIDATE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CandidateConversation(Base):
    __tablename__ = "candidate_conversations"
    __table_args__ = (
        UniqueConstraint("source_visitor_session_id", name="uq_candidate_conv_source_session"),
        CheckConstraint(_in("status", CONVERSATION_STATUSES), name="ck_candidate_conv_status"),
        CheckConstraint("next_message_sequence >= 1", name="ck_candidate_conv_next_sequence"),
        CheckConstraint(
            "source_visitor_session_id IS NULL OR consent_given_at IS NOT NULL",
            name="ck_candidate_conv_claim_consent",
        ),
        Index("ix_candidate_conv_candidate", "candidate_id", "updated_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False
    )
    # Deliberately not a foreign key: the visitor session is purged by the retention job.
    # The unique value makes a claim idempotent and prevents claiming one session twice.
    source_visitor_session_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    title: Mapped[str | None] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="ACTIVE")
    next_message_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CandidateMessage(Base):
    __tablename__ = "candidate_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "sequence", name="uq_candidate_message_sequence"),
        CheckConstraint("role IN ('user','assistant')", name="ck_candidate_message_role"),
        CheckConstraint("sequence >= 1", name="ck_candidate_message_sequence_positive"),
        CheckConstraint(
            "detected_language IS NULL OR " + _in("detected_language", LANGUAGES),
            name="ck_candidate_message_language",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_conversations.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    detected_language: Mapped[str | None] = mapped_column(String(10))
    original_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # kept when copied from a visitor session
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
