"""Payment terms, publication status and validity period for tuition and admission rules (additive).

Revision ID: 0011_payment_terms_validity
Revises: 0010_documents_ingestion
"""
import sqlalchemy as sa
from alembic import op

revision = "0011_payment_terms_validity"
down_revision = "0010_documents_ingestion"
branch_labels = None
depends_on = None

PUBLICATION = "publication_status IN ('DRAFT','PUBLISHED','ARCHIVED')"
VALIDITY = "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from"


def _add_publication(table, prefix):
    # Existing rows keep today's behaviour: PUBLISHED, still gated by their verified source.
    with op.batch_alter_table(table) as batch:
        batch.add_column(sa.Column("publication_status", sa.String(10), nullable=False, server_default="PUBLISHED"))
        batch.add_column(sa.Column("valid_from", sa.DateTime(timezone=True)))
        batch.add_column(sa.Column("valid_to", sa.DateTime(timezone=True)))
        batch.create_check_constraint(f"ck_{prefix}_publication", PUBLICATION)
        batch.create_check_constraint(f"ck_{prefix}_validity", VALIDITY)


def upgrade():
    _add_publication("program_tuition", "tuition")
    _add_publication("program_admission_rules", "rule")

    op.create_table("program_payment_terms",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("program_id", sa.Uuid(as_uuid=True), sa.ForeignKey("programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label", sa.String(180), nullable=False),
        sa.Column("academic_year", sa.String(9), nullable=False),
        sa.Column("payment_mode", sa.String(14), nullable=False),
        sa.Column("installments_count", sa.Integer()),
        sa.Column("first_payment_percent", sa.Numeric(5, 2)),
        sa.Column("schedule_description", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("official_source_url", sa.String(500)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("publication_status", sa.String(10), nullable=False, server_default="PUBLISHED"),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("program_id", "label", "academic_year", name="uq_payment_program_label_year"),
        sa.CheckConstraint("payment_mode IN ('FULL','INSTALLMENTS')", name="ck_payment_mode"),
        sa.CheckConstraint("(payment_mode = 'FULL' AND installments_count IS NULL) OR "
                           "(payment_mode = 'INSTALLMENTS' AND installments_count BETWEEN 2 AND 12)",
                           name="ck_payment_installments"),
        sa.CheckConstraint("first_payment_percent IS NULL OR (first_payment_percent > 0 AND first_payment_percent <= 100)",
                           name="ck_payment_first_percent"),
        sa.CheckConstraint("length(academic_year) = 9", name="ck_payment_year_length"),
        sa.CheckConstraint(PUBLICATION, name="ck_payment_publication"),
        sa.CheckConstraint(VALIDITY, name="ck_payment_validity"))
    op.create_index("ix_payment_program_year", "program_payment_terms", ["program_id", "academic_year"])


def downgrade():
    op.drop_index("ix_payment_program_year", table_name="program_payment_terms")
    op.drop_table("program_payment_terms")
    for table, prefix in (("program_admission_rules", "rule"), ("program_tuition", "tuition")):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"ck_{prefix}_validity", type_="check")
            batch.drop_constraint(f"ck_{prefix}_publication", type_="check")
            batch.drop_column("valid_to")
            batch.drop_column("valid_from")
            batch.drop_column("publication_status")
