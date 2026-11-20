"""Database-wide atomic fixed-window counters for anonymous traffic.

Revision ID: 0007_abuse_limits
Revises: 0006_candidate_accounts
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_abuse_limits"
down_revision = "0006_candidate_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("rate_limit_buckets",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("hits >= 1", name="ck_rate_limit_hits_positive"))
    op.create_index("ix_rate_limit_buckets_expires", "rate_limit_buckets", ["expires_at"])


def downgrade():
    op.drop_index("ix_rate_limit_buckets_expires", table_name="rate_limit_buckets")
    op.drop_table("rate_limit_buckets")
