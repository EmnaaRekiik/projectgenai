"""Candidate requests: preinscription, equivalence, appointment and interview outcome.

Statuses are plain strings guarded by CHECK constraints (same convention as the rest of the
project). They mirror docs/PROCESSUS_METIER.md. Official decisions are always recorded by staff.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PREREGISTRATION_STATUSES = ("DRAFT", "SUBMITTED", "COMPLETE", "VALIDATED", "REJECTED", "CANCELLED")
EQUIVALENCE_STATUSES = ("DRAFT", "SUBMITTED", "IN_REVIEW", "INFO_REQUESTED", "ACCEPTED", "REFUSED")
APPOINTMENT_STATUSES = ("PROPOSED", "CONFIRMED", "RESCHEDULED", "CANCELLED", "COMPLETED")
INTERVIEW_STATUSES = ("PLANNED", "QCM_SENT", "QCM_DONE", "HELD", "RESULT_RECORDED")
INTERVIEW_DECISIONS = ("ADMITTED", "WAITLIST", "REFUSED", "INFO_NEEDED")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class Preregistration(Base):
    __tablename__ = "preregistrations"
    __table_args__ = (
        CheckConstraint(_in("status", PREREGISTRATION_STATUSES), name="ck_prereg_status"),
        CheckConstraint(
            "status = 'DRAFT' OR consent_given_at IS NOT NULL", name="ck_prereg_consent_required"
        ),
        Index("ix_prereg_candidate", "candidate_id"),
        Index("ix_prereg_program_status", "program_id", "status"),
        Index(
            "uq_prereg_active_candidate_program",
            "candidate_id",
            "program_id",
            unique=True,
            postgresql_where=text("status NOT IN ('REJECTED','CANCELLED')"),
            sqlite_where=text("status NOT IN ('REJECTED','CANCELLED')"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False
    )
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EquivalenceRequest(Base):
    __tablename__ = "equivalence_requests"
    __table_args__ = (
        CheckConstraint(_in("status", EQUIVALENCE_STATUSES), name="ck_equivalence_status"),
        Index("ix_equivalence_candidate", "candidate_id"),
        Index("ix_equivalence_status", "status"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False
    )
    target_program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL")
    )
    origin_diploma: Mapped[str] = mapped_column(String(180), nullable=False)
    origin_institution: Mapped[str] = mapped_column(String(180), nullable=False)
    origin_country: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    decision_note: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Appointment(Base):
    __tablename__ = "appointments"
    __table_args__ = (
        CheckConstraint(_in("status", APPOINTMENT_STATUSES), name="ck_appointment_status"),
        CheckConstraint("ends_at > starts_at", name="ck_appointment_time_order"),
        Index("ix_appointment_candidate", "candidate_id"),
        Index("ix_appointment_manager_start", "manager_id", "starts_at"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidate_users.id", ondelete="CASCADE"), nullable=False
    )
    preregistration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("preregistrations.id", ondelete="SET NULL")
    )
    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROPOSED")
    location_or_link: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InterviewResult(Base):
    __tablename__ = "interview_results"
    __table_args__ = (
        UniqueConstraint("appointment_id", name="uq_interview_appointment"),
        CheckConstraint(_in("status", INTERVIEW_STATUSES), name="ck_interview_status"),
        CheckConstraint(
            "decision IS NULL OR " + _in("decision", INTERVIEW_DECISIONS),
            name="ck_interview_decision",
        ),
        CheckConstraint(
            "qcm_score IS NULL OR (qcm_score >= 0 AND qcm_score <= 100)",
            name="ck_interview_qcm_score",
        ),
        CheckConstraint(
            "decision IS NULL OR status = 'RESULT_RECORDED'", name="ck_interview_decision_status"
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    appointment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("appointments.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PLANNED")
    qcm_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    summary: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(16))
    observations: Mapped[str | None] = mapped_column(Text)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
