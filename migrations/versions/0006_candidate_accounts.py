"""Candidate signup/login, private profile, optional verifiable email challenge.

Revision ID: 0006_candidate_accounts
Revises: 0005_academic_details
"""

import sqlalchemy as sa
from alembic import op

revision = "0006_candidate_accounts"
down_revision = "0005_academic_details"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "candidate_users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("email_verified_at", sa.DateTime(timezone=True)),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("education_level", sa.String(120)),
        sa.Column("interests", sa.Text()),
        sa.Column("career_goal", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("failed_login_count >= 0", name="ck_candidate_failed_login_count"),
    )
    op.create_table(
        "candidate_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("candidate_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_candidate_sessions_user_id", "candidate_sessions", ["user_id"])
    op.create_index("ix_candidate_sessions_expires", "candidate_sessions", ["expires_at"])
    op.create_table(
        "candidate_email_tokens",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("candidate_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), unique=True, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_candidate_email_tokens_user_id", "candidate_email_tokens", ["user_id"])
    op.create_index("ix_candidate_email_token_expires", "candidate_email_tokens", ["expires_at"])


def downgrade():
    op.drop_index("ix_candidate_email_token_expires", table_name="candidate_email_tokens")
    op.drop_index("ix_candidate_email_tokens_user_id", table_name="candidate_email_tokens")
    op.drop_table("candidate_email_tokens")
    op.drop_index("ix_candidate_sessions_expires", table_name="candidate_sessions")
    op.drop_index("ix_candidate_sessions_user_id", table_name="candidate_sessions")
    op.drop_table("candidate_sessions")
    op.drop_table("candidate_users")
