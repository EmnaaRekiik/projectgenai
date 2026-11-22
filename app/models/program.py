import uuid
from datetime import datetime
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:
    from app.models.institution import Institution


class Program(Base):
    __tablename__ = "programs"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_program_institution_code"),
        CheckConstraint("duration_years BETWEEN 1 AND 10", name="ck_program_duration"),
        CheckConstraint(
            "level IN ('LICENCE', 'PREPARATORY', 'ENGINEERING', 'OTHER')",
            name="ck_program_level",
        ),
        CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_program_status"),
        CheckConstraint(
            "status <> 'PUBLISHED' OR (official_source_url IS NOT NULL "
            "AND verified_at IS NOT NULL)",
            name="ck_program_published_has_evidence",
        ),
        Index("ix_program_institution_level", "institution_id", "level"),
        Index("ix_program_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    duration_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    official_source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    institution: Mapped["Institution"] = relationship(back_populates="programs")
