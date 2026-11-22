"""Add isolated staff identities, login lockout and revocable sessions.

Revision ID: 0004_staff_auth
Revises: 0003_chat_lease
Create Date: 2026-11-20
"""

import sqlalchemy as sa
from alembic import op

revision = "0004_staff_auth"
down_revision = "0003_chat_lease"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column(
            "institution_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("institutions.id", ondelete="RESTRICT"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "role IN ('PLATFORM_ADMIN','ACADEMIC_IIT','ACADEMIC_ISB','INTERVIEW_MANAGER','DIRECTION')",
            name="ck_staff_role",
        ),
        sa.CheckConstraint(
            "role NOT IN ('ACADEMIC_IIT','ACADEMIC_ISB') OR institution_id IS NOT NULL",
            name="ck_staff_academic_institution",
        ),
        sa.CheckConstraint("failed_login_count >= 0", name="ck_staff_login_count"),
    )
    op.create_table(
        "staff_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("staff_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_staff_sessions_user_id", "staff_sessions", ["user_id"])
    op.create_index("ix_staff_sessions_expires_at", "staff_sessions", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_staff_sessions_expires_at", table_name="staff_sessions")
    op.drop_index("ix_staff_sessions_user_id", table_name="staff_sessions")
    op.drop_table("staff_sessions")
    op.drop_table("staff_users")
