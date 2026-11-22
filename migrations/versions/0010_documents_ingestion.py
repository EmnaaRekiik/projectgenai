"""Documents, versions, chunks and indexing jobs. No pgvector dependency (additive).

Revision ID: 0010_documents_ingestion
Revises: 0009_profile_conversations
"""
import sqlalchemy as sa
from alembic import op

revision = "0010_documents_ingestion"
down_revision = "0009_profile_conversations"
branch_labels = None
depends_on = None

ACTIVE_JOB = "status IN ('PENDING','RUNNING')"


def _ts(name):
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade():
    op.create_table("documents",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(220), nullable=False),
        sa.Column("doc_type", sa.String(16), nullable=False),
        sa.Column("institution_id", sa.Uuid(as_uuid=True), sa.ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("program_id", sa.Uuid(as_uuid=True), sa.ForeignKey("programs.id", ondelete="SET NULL")),
        sa.Column("language", sa.String(10)),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("created_by", sa.Uuid(as_uuid=True), sa.ForeignKey("staff_users.id", ondelete="SET NULL")),
        _ts("created_at"), _ts("updated_at"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("doc_type IN ('BROCHURE','FAQ','REGULATION','TUITION_GRID','PROGRAM_SHEET','OTHER')", name="ck_document_type"),
        sa.CheckConstraint("status IN ('DRAFT','PUBLISHED','ARCHIVED')", name="ck_document_status"))
    op.create_index("ix_document_institution_status", "documents", ["institution_id", "status"])
    op.create_index("ix_document_program", "documents", ["program_id"])

    op.create_table("document_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.Uuid(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True)),
        sa.Column("valid_to", sa.DateTime(timezone=True)),
        sa.Column("change_note", sa.Text()),
        sa.Column("uploaded_by", sa.Uuid(as_uuid=True), sa.ForeignKey("staff_users.id", ondelete="SET NULL")),
        _ts("created_at"),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        sa.UniqueConstraint("document_id", "sha256", name="uq_document_version_checksum"),
        sa.CheckConstraint("version_number >= 1", name="ck_document_version_positive"),
        sa.CheckConstraint("size_bytes > 0", name="ck_document_version_size"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_document_version_sha256"),
        sa.CheckConstraint("valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from", name="ck_document_version_validity"))
    op.create_index("uq_document_current_version", "document_versions", ["document_id"], unique=True,
                    postgresql_where=sa.text("is_current"), sqlite_where=sa.text("is_current"))

    op.create_table("document_chunks",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("document_version_id", sa.Uuid(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("page_number", sa.Integer()),
        sa.Column("section_title", sa.String(220)),
        sa.Column("token_count", sa.Integer()),
        sa.Column("embedding_model", sa.String(120)),
        sa.Column("embedded_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        sa.UniqueConstraint("document_version_id", "chunk_index", name="uq_document_chunk_index"),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunk_index"),
        sa.CheckConstraint("length(content_hash) = 64", name="ck_document_chunk_hash"),
        sa.CheckConstraint("embedded_at IS NULL OR embedding_model IS NOT NULL", name="ck_document_chunk_embedding_model"))

    op.create_table("ingestion_jobs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("document_id", sa.Uuid(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("document_version_id", sa.Uuid(as_uuid=True), sa.ForeignKey("document_versions.id", ondelete="SET NULL")),
        sa.Column("action", sa.String(10), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text()),
        sa.Column("locked_by", sa.String(120)),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        _ts("scheduled_at"),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        _ts("created_at"),
        sa.CheckConstraint("action IN ('ADD','UPDATE','DELETE')", name="ck_ingestion_action"),
        sa.CheckConstraint("status IN ('PENDING','RUNNING','SUCCEEDED','FAILED','CANCELLED')", name="ck_ingestion_status"),
        sa.CheckConstraint("attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts", name="ck_ingestion_attempts"),
        sa.CheckConstraint("status <> 'FAILED' OR error_message IS NOT NULL", name="ck_ingestion_failed_has_error"),
        sa.CheckConstraint("action = 'DELETE' OR document_version_id IS NOT NULL OR status IN ('SUCCEEDED','FAILED','CANCELLED')", name="ck_ingestion_version_required"))
    op.create_index("ix_ingestion_poll", "ingestion_jobs", ["status", "scheduled_at"])
    op.create_index("ix_ingestion_document", "ingestion_jobs", ["document_id"])
    op.create_index("uq_ingestion_active_version_action", "ingestion_jobs", ["document_version_id", "action"], unique=True,
                    postgresql_where=sa.text(ACTIVE_JOB), sqlite_where=sa.text(ACTIVE_JOB))


def downgrade():
    op.drop_index("uq_ingestion_active_version_action", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_document", table_name="ingestion_jobs")
    op.drop_index("ix_ingestion_poll", table_name="ingestion_jobs")
    op.drop_table("ingestion_jobs")
    op.drop_table("document_chunks")
    op.drop_index("uq_document_current_version", table_name="document_versions")
    op.drop_table("document_versions")
    op.drop_index("ix_document_program", table_name="documents")
    op.drop_index("ix_document_institution_status", table_name="documents")
    op.drop_table("documents")
