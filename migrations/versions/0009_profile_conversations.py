"""Academic profile, candidate-owned conversations, one active preinscription per programme (additive).

Revision ID: 0009_profile_conversations
Revises: 0008_admission_requests
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_profile_conversations"
down_revision = "0008_admission_requests"
branch_labels = None
depends_on = None

LANGS = "('fr','derja','arabizi','mixed')"
ACTIVE_PREREG = "status NOT IN ('REJECTED','CANCELLED')"


def _ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table(
        "academic_profiles",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("candidate_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bac_series", sa.String(60)),
        sa.Column("bac_year", sa.Integer()),
        sa.Column("average_grade", sa.Numeric(5, 2)),
        sa.Column("favorite_subjects", sa.Text()),
        sa.Column("interests", sa.Text()),
        sa.Column("career_goal", sa.String(500)),
        sa.Column("constraints_note", sa.Text()),
        sa.Column("preferred_language", sa.String(10)),
        sa.Column("source", sa.String(10), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("candidate_id", name="uq_academic_profile_candidate"),
        sa.CheckConstraint(
            "average_grade IS NULL OR (average_grade >= 0 AND average_grade <= 20)",
            name="ck_profile_grade",
        ),
        sa.CheckConstraint(
            "bac_year IS NULL OR (bac_year >= 1990 AND bac_year <= 2100)",
            name="ck_profile_bac_year",
        ),
        sa.CheckConstraint(
            f"preferred_language IS NULL OR preferred_language IN {LANGS}",
            name="ck_profile_language",
        ),
        sa.CheckConstraint("source IN ('CANDIDATE','AGENT','STAFF')", name="ck_profile_source"),
    )

    op.create_table(
        "candidate_conversations",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "candidate_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("candidate_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_visitor_session_id", sa.Uuid(as_uuid=True)),
        sa.Column("consent_given_at", sa.DateTime(timezone=True)),
        sa.Column("claimed_at", sa.DateTime(timezone=True)),
        sa.Column("title", sa.String(180)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("next_message_sequence", sa.Integer(), nullable=False),
        _ts("created_at"),
        _ts("updated_at"),
        sa.UniqueConstraint("source_visitor_session_id", name="uq_candidate_conv_source_session"),
        sa.CheckConstraint("status IN ('ACTIVE','ARCHIVED')", name="ck_candidate_conv_status"),
        sa.CheckConstraint("next_message_sequence >= 1", name="ck_candidate_conv_next_sequence"),
        sa.CheckConstraint(
            "source_visitor_session_id IS NULL OR consent_given_at IS NOT NULL",
            name="ck_candidate_conv_claim_consent",
        ),
    )
    op.create_index(
        "ix_candidate_conv_candidate", "candidate_conversations", ["candidate_id", "updated_at"]
    )

    op.create_table(
        "candidate_messages",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("candidate_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("detected_language", sa.String(10)),
        sa.Column("original_created_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        sa.UniqueConstraint("conversation_id", "sequence", name="uq_candidate_message_sequence"),
        sa.CheckConstraint("role IN ('user','assistant')", name="ck_candidate_message_role"),
        sa.CheckConstraint("sequence >= 1", name="ck_candidate_message_sequence_positive"),
        sa.CheckConstraint(
            f"detected_language IS NULL OR detected_language IN {LANGS}",
            name="ck_candidate_message_language",
        ),
    )

    op.create_index(
        "uq_prereg_active_candidate_program",
        "preregistrations",
        ["candidate_id", "program_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_PREREG),
        sqlite_where=sa.text(ACTIVE_PREREG),
    )


def downgrade():
    op.drop_index("uq_prereg_active_candidate_program", table_name="preregistrations")
    op.drop_table("candidate_messages")
    op.drop_index("ix_candidate_conv_candidate", table_name="candidate_conversations")
    op.drop_table("candidate_conversations")
    op.drop_table("academic_profiles")
