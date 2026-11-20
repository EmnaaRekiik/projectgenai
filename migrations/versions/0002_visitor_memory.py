"""Anonymous visitor sessions and bounded conversation memory.

Revision ID: 0002_visitor_memory
Revises: 0001_catalogue
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0002_visitor_memory"
down_revision = "0001_catalogue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visitor_sessions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_message_sequence", sa.Integer(), nullable=False),
        sa.CheckConstraint("next_message_sequence >= 1", name="ck_visitor_next_sequence"),
    )
    op.create_index("ix_visitor_sessions_expires_at", "visitor_sessions", ["expires_at"])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("session_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("visitor_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.UniqueConstraint("session_id", "sequence", name="uq_conversation_session_sequence"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_conversation_message_role"),
        sa.CheckConstraint("sequence >= 1", name="ck_conversation_sequence_positive"),
    )
    op.create_index("ix_conversation_messages_session_id_sequence", "conversation_messages",
                    ["session_id", "sequence"])


def downgrade() -> None:
    op.drop_index("ix_conversation_messages_session_id_sequence", table_name="conversation_messages")
    op.drop_table("conversation_messages")
    op.drop_index("ix_visitor_sessions_expires_at", table_name="visitor_sessions")
    op.drop_table("visitor_sessions")
