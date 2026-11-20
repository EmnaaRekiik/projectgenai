"""Persistent staff identity and revocable opaque access tokens."""
import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class StaffRole(str, Enum):
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    ACADEMIC_IIT = "ACADEMIC_IIT"
    ACADEMIC_ISB = "ACADEMIC_ISB"
    INTERVIEW_MANAGER = "INTERVIEW_MANAGER"
    DIRECTION = "DIRECTION"


class StaffUser(Base):
    __tablename__ = "staff_users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('PLATFORM_ADMIN','ACADEMIC_IIT','ACADEMIC_ISB','INTERVIEW_MANAGER','DIRECTION')",
            name="ck_staff_role",
        ),
        CheckConstraint(
            "role NOT IN ('ACADEMIC_IIT','ACADEMIC_ISB') OR institution_id IS NOT NULL",
            name="ck_staff_academic_institution",
        ),
        CheckConstraint("failed_login_count >= 0", name="ck_staff_login_count"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sessions: Mapped[list["StaffSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class StaffSession(Base):
    __tablename__ = "staff_sessions"
    __table_args__ = (Index("ix_staff_sessions_expires_at", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("staff_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user: Mapped[StaffUser] = relationship(back_populates="sessions")
