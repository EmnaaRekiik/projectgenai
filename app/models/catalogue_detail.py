"""Structured academic information. Draft/unverified rows are never public."""
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VerifiedDetail:
    """Shared source-evidence fields. Presence of both makes a detail publishable."""
    official_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProgramSpecialization(VerifiedDetail, Base):
    __tablename__ = "program_specializations"
    __table_args__ = (
        UniqueConstraint("program_id", "code", name="uq_specialization_program_code"),
        UniqueConstraint("id", "program_id", name="uq_specialization_id_program"),
        Index("ix_specialization_program", "program_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProgramCourse(VerifiedDetail, Base):
    __tablename__ = "program_courses"
    __table_args__ = (
        UniqueConstraint("program_id", "code", "semester", name="uq_course_program_code_semester"),
        ForeignKeyConstraint(["specialization_id", "program_id"],
                             ["program_specializations.id", "program_specializations.program_id"],
                             ondelete="RESTRICT", name="fk_course_same_program_specialization"),
        CheckConstraint("semester BETWEEN 1 AND 20", name="ck_course_semester"),
        CheckConstraint("credits IS NULL OR (credits >= 0 AND credits <= 60)", name="ck_course_credits"),
        Index("ix_course_program_semester", "program_id", "semester"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    specialization_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProgramAdmissionRule(VerifiedDetail, Base):
    __tablename__ = "program_admission_rules"
    __table_args__ = (
        CheckConstraint("kind IN ('ADMISSION','PREREQUISITE','DOCUMENT')", name="ck_rule_kind"),
        Index("ix_rule_program_kind", "program_id", "kind"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ProgramTuition(VerifiedDetail, Base):
    __tablename__ = "program_tuition"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_tuition_amount_nonnegative"),
        UniqueConstraint("program_id", "label", "academic_year", "currency", name="uq_tuition_program_charge_year_currency"),
        CheckConstraint("length(academic_year) = 9", name="ck_tuition_year_length"),
        Index("ix_tuition_program_year", "program_id", "academic_year"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("programs.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="TND")
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
