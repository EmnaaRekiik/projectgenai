"""Structured academic information. Draft/unverified rows are never public."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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


class VerifiedDetail:
    """Shared source-evidence fields. Presence of both makes a detail publishable."""

    official_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PublishableDetail:
    """Explicit publication status and validity period (T7).

    Public visibility = programme PUBLISHED + verified source + publication_status PUBLISHED
    + today inside [valid_from, valid_to] (an open bound means unlimited).
    """

    publication_status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="PUBLISHED", server_default="PUBLISHED"
    )
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


PUBLICATION_CHECK = "publication_status IN ('DRAFT','PUBLISHED','ARCHIVED')"
VALIDITY_CHECK = "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from"


class ProgramSpecialization(VerifiedDetail, Base):
    __tablename__ = "program_specializations"
    __table_args__ = (
        UniqueConstraint("program_id", "code", name="uq_specialization_program_code"),
        UniqueConstraint("id", "program_id", name="uq_specialization_id_program"),
        Index("ix_specialization_program", "program_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProgramCourse(VerifiedDetail, Base):
    __tablename__ = "program_courses"
    __table_args__ = (
        UniqueConstraint("program_id", "code", "semester", name="uq_course_program_code_semester"),
        ForeignKeyConstraint(
            ["specialization_id", "program_id"],
            ["program_specializations.id", "program_specializations.program_id"],
            ondelete="RESTRICT",
            name="fk_course_same_program_specialization",
        ),
        CheckConstraint("semester BETWEEN 1 AND 20", name="ck_course_semester"),
        CheckConstraint(
            "credits IS NULL OR (credits >= 0 AND credits <= 60)", name="ck_course_credits"
        ),
        Index("ix_course_program_semester", "program_id", "semester"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    specialization_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    credits: Mapped[int | None] = mapped_column(Integer)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProgramAdmissionRule(PublishableDetail, VerifiedDetail, Base):
    __tablename__ = "program_admission_rules"
    __table_args__ = (
        CheckConstraint("kind IN ('ADMISSION','PREREQUISITE','DOCUMENT')", name="ck_rule_kind"),
        CheckConstraint(PUBLICATION_CHECK, name="ck_rule_publication"),
        CheckConstraint(VALIDITY_CHECK, name="ck_rule_validity"),
        Index("ix_rule_program_kind", "program_id", "kind"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProgramTuition(PublishableDetail, VerifiedDetail, Base):
    __tablename__ = "program_tuition"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_tuition_amount_nonnegative"),
        CheckConstraint(PUBLICATION_CHECK, name="ck_tuition_publication"),
        CheckConstraint(VALIDITY_CHECK, name="ck_tuition_validity"),
        UniqueConstraint(
            "program_id",
            "label",
            "academic_year",
            "currency",
            name="uq_tuition_program_charge_year_currency",
        ),
        CheckConstraint("length(academic_year) = 9", name="ck_tuition_year_length"),
        Index("ix_tuition_program_year", "program_id", "academic_year"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="TND")
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ProgramPaymentTerm(PublishableDetail, VerifiedDetail, Base):
    """How tuition can be paid: in full or by instalments."""

    __tablename__ = "program_payment_terms"
    __table_args__ = (
        UniqueConstraint(
            "program_id", "label", "academic_year", name="uq_payment_program_label_year"
        ),
        CheckConstraint("payment_mode IN ('FULL','INSTALLMENTS')", name="ck_payment_mode"),
        CheckConstraint(
            "(payment_mode = 'FULL' AND installments_count IS NULL) OR "
            "(payment_mode = 'INSTALLMENTS' AND installments_count BETWEEN 2 AND 12)",
            name="ck_payment_installments",
        ),
        CheckConstraint(
            "first_payment_percent IS NULL OR (first_payment_percent > 0 AND first_payment_percent <= 100)",
            name="ck_payment_first_percent",
        ),
        CheckConstraint("length(academic_year) = 9", name="ck_payment_year_length"),
        CheckConstraint(PUBLICATION_CHECK, name="ck_payment_publication"),
        CheckConstraint(VALIDITY_CHECK, name="ck_payment_validity"),
        Index("ix_payment_program_year", "program_id", "academic_year"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programs.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(180), nullable=False)
    academic_year: Mapped[str] = mapped_column(String(9), nullable=False)
    payment_mode: Mapped[str] = mapped_column(String(14), nullable=False)
    installments_count: Mapped[int | None] = mapped_column(Integer)
    first_payment_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    schedule_description: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
