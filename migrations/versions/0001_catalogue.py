"""Initial IIT/ISB academic catalogue.

Revision ID: 0001_catalogue
Revises:
Create Date: 2026-11-20
"""

import sqlalchemy as sa

from alembic import op

revision = "0001_catalogue"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "institutions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "programs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("institution_id", sa.Uuid(as_uuid=True), sa.ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("level", sa.String(20), nullable=False),
        sa.Column("duration_years", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("official_source_url", sa.String(500), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("institution_id", "code", name="uq_program_institution_code"),
        sa.CheckConstraint("duration_years BETWEEN 1 AND 10", name="ck_program_duration"),
        sa.CheckConstraint("level IN ('LICENCE', 'PREPARATORY', 'ENGINEERING', 'OTHER')", name="ck_program_level"),
        sa.CheckConstraint("status IN ('DRAFT', 'PUBLISHED', 'ARCHIVED')", name="ck_program_status"),
        sa.CheckConstraint(
            "status <> 'PUBLISHED' OR (official_source_url IS NOT NULL AND verified_at IS NOT NULL)",
            name="ck_program_published_has_evidence",
        ),
    )
    op.create_index("ix_program_institution_level", "programs", ["institution_id", "level"])
    op.create_index("ix_program_status", "programs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_program_status", table_name="programs")
    op.drop_index("ix_program_institution_level", table_name="programs")
    op.drop_table("programs")
    op.drop_table("institutions")
