"""Normalized specialities, course catalogue, admission/prerequisites and official tuition.

Revision ID: 0005_academic_details
Revises: 0004_staff_auth
"""

import sqlalchemy as sa
from alembic import op

revision = "0005_academic_details"
down_revision = "0004_staff_auth"
branch_labels = None
depends_on = None


def _common():
    return [
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "program_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("programs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("official_source_url", sa.String(500)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade():
    op.create_table(
        "program_specializations",
        *_common(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text()),
        sa.UniqueConstraint("program_id", "code", name="uq_specialization_program_code"),
        sa.UniqueConstraint("id", "program_id", name="uq_specialization_id_program"),
    )
    op.create_index("ix_specialization_program", "program_specializations", ["program_id"])
    op.create_table(
        "program_courses",
        *_common(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("specialization_id", sa.Uuid(as_uuid=True)),
        sa.Column("semester", sa.Integer(), nullable=False),
        sa.Column("credits", sa.Integer()),
        sa.Column("description", sa.Text()),
        sa.UniqueConstraint(
            "program_id", "code", "semester", name="uq_course_program_code_semester"
        ),
        sa.ForeignKeyConstraint(
            ["specialization_id", "program_id"],
            ["program_specializations.id", "program_specializations.program_id"],
            ondelete="RESTRICT",
            name="fk_course_same_program_specialization",
        ),
        sa.CheckConstraint("semester BETWEEN 1 AND 20", name="ck_course_semester"),
        sa.CheckConstraint(
            "credits IS NULL OR (credits >= 0 AND credits <= 60)", name="ck_course_credits"
        ),
    )
    op.create_index("ix_course_program_semester", "program_courses", ["program_id", "semester"])
    op.create_table(
        "program_admission_rules",
        *_common(),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.CheckConstraint("kind IN ('ADMISSION','PREREQUISITE','DOCUMENT')", name="ck_rule_kind"),
    )
    op.create_index("ix_rule_program_kind", "program_admission_rules", ["program_id", "kind"])
    op.create_table(
        "program_tuition",
        *_common(),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint("amount >= 0", name="ck_tuition_amount_nonnegative"),
        sa.UniqueConstraint(
            "program_id",
            "label",
            "academic_year",
            "currency",
            name="uq_tuition_program_charge_year_currency",
        ),
        sa.CheckConstraint("length(academic_year) = 9", name="ck_tuition_year_length"),
    )
    op.create_index("ix_tuition_program_year", "program_tuition", ["program_id", "academic_year"])


def downgrade():
    for table, index in [
        ("program_tuition", "ix_tuition_program_year"),
        ("program_admission_rules", "ix_rule_program_kind"),
        ("program_courses", "ix_course_program_semester"),
        ("program_specializations", "ix_specialization_program"),
    ]:
        op.drop_index(index, table_name=table)
        op.drop_table(table)
