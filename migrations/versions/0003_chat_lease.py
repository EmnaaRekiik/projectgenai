"""Serialize chat turns by a short-lived PostgreSQL lease.

Revision ID: 0003_chat_lease
Revises: 0002_visitor_memory
Create Date: 2026-11-20
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_chat_lease"
down_revision = "0002_visitor_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("visitor_sessions", sa.Column("chat_request_id", sa.Uuid(as_uuid=True), nullable=True))
    op.add_column("visitor_sessions", sa.Column("chat_lease_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("visitor_sessions", "chat_lease_until")
    op.drop_column("visitor_sessions", "chat_request_id")
