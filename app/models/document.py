"""Documents imported by staff, their versions, text chunks and indexing jobs (RAG preparation).

Design choice: nothing here depends on the pgvector extension. Chunks and the jobs that
(re)build the index are tracked in plain tables; the vector storage itself is added later,
once the embedding model is chosen, by a separate additive migration.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

DOCUMENT_TYPES = ("BROCHURE", "FAQ", "REGULATION", "TUITION_GRID", "PROGRAM_SHEET", "OTHER")
DOCUMENT_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")
JOB_ACTIONS = ("ADD", "UPDATE", "DELETE")
JOB_STATUSES = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED")
ACTIVE_JOB = "status IN ('PENDING','RUNNING')"


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ",".join(f"'{v}'" for v in values) + ")"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(_in("doc_type", DOCUMENT_TYPES), name="ck_document_type"),
        CheckConstraint(_in("status", DOCUMENT_STATUSES), name="ck_document_status"),
        Index("ix_document_institution_status", "institution_id", "status"),
        Index("ix_document_program", "program_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(220), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(16), nullable=False, default="OTHER")
    institution_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False
    )
    program_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("programs.id", ondelete="SET NULL")
    )
    language: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="DRAFT")
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # soft delete


class DocumentVersion(Base):
    __tablename__ = "document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_number", name="uq_document_version_number"),
        UniqueConstraint("document_id", "sha256", name="uq_document_version_checksum"),
        CheckConstraint("version_number >= 1", name="ck_document_version_positive"),
        CheckConstraint("size_bytes > 0", name="ck_document_version_size"),
        CheckConstraint("length(sha256) = 64", name="ck_document_version_sha256"),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to > valid_from",
            name="ck_document_version_validity",
        ),
        Index(
            "uq_document_current_version",
            "document_id",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current"),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    change_note: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        UniqueConstraint("document_version_id", "chunk_index", name="uq_document_chunk_index"),
        CheckConstraint("chunk_index >= 0", name="ck_document_chunk_index"),
        CheckConstraint("length(content_hash) = 64", name="ck_document_chunk_hash"),
        CheckConstraint(
            "embedded_at IS NULL OR embedding_model IS NOT NULL",
            name="ck_document_chunk_embedding_model",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    section_title: Mapped[str | None] = mapped_column(String(220))
    token_count: Mapped[int | None] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(120))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"
    __table_args__ = (
        CheckConstraint(_in("action", JOB_ACTIONS), name="ck_ingestion_action"),
        CheckConstraint(_in("status", JOB_STATUSES), name="ck_ingestion_status"),
        CheckConstraint(
            "attempts >= 0 AND max_attempts >= 1 AND attempts <= max_attempts",
            name="ck_ingestion_attempts",
        ),
        CheckConstraint(
            "status <> 'FAILED' OR error_message IS NOT NULL", name="ck_ingestion_failed_has_error"
        ),
        CheckConstraint(
            "action = 'DELETE' OR document_version_id IS NOT NULL OR status IN ('SUCCEEDED','FAILED','CANCELLED')",
            name="ck_ingestion_version_required",
        ),
        Index("ix_ingestion_poll", "status", "scheduled_at"),
        Index("ix_ingestion_document", "document_id"),
        Index(
            "uq_ingestion_active_version_action",
            "document_version_id",
            "action",
            unique=True,
            postgresql_where=text(ACTIVE_JOB),
            sqlite_where=text(ACTIVE_JOB),
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    document_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("document_versions.id", ondelete="SET NULL")
    )
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    error_message: Mapped[str | None] = mapped_column(Text)
    locked_by: Mapped[str | None] = mapped_column(String(120))  # worker identifier
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # lease, lets a crashed job be retaken
    scheduled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
