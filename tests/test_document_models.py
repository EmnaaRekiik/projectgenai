"""Rules of the document, version, chunk and indexing job tables (migration 0010)."""

import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import Document, DocumentChunk, DocumentVersion, IngestionJob, Institution

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def db(client, test_engine):
    with sessionmaker(bind=test_engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def doc(db):
    inst = Institution(code="IIT", name="Institute")
    db.add(inst)
    db.flush()
    d = Document(title="Brochure test", doc_type="BROCHURE", institution_id=inst.id)
    db.add(d)
    db.commit()
    return d


def version(doc, n, content="a", current=False, **kw):
    return DocumentVersion(
        document_id=doc.id,
        version_number=n,
        storage_path=f"docs/{n}.pdf",
        original_filename="b.pdf",
        mime_type="application/pdf",
        size_bytes=1234,
        sha256=sha(f"{content}{n}"),
        is_current=current,
        **kw,
    )


def _fails(db, obj):
    db.add(obj)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_document_type_and_status_are_checked(db, doc):
    _fails(db, Document(title="x", doc_type="VIDEO", institution_id=doc.institution_id))
    _fails(db, Document(title="x", status="LIVE", institution_id=doc.institution_id))


def test_versions_are_unique_and_only_one_is_current(db, doc):
    db.add(version(doc, 1, current=True))
    db.commit()
    _fails(db, version(doc, 1))  # same version number
    _fails(db, version(doc, 2, current=True))  # second current version
    db.add(version(doc, 2, current=False))
    db.commit()
    # Same file uploaded twice for one document is detected by its checksum.
    dup = version(doc, 3)
    dup.sha256 = sha("a1")
    _fails(db, dup)


def test_version_validity_size_and_hash_checks(db, doc):
    _fails(db, version(doc, 1, valid_from=NOW, valid_to=NOW - timedelta(days=1)))
    bad = version(doc, 2)
    bad.size_bytes = 0
    _fails(db, bad)
    bad = version(doc, 3)
    bad.sha256 = "short"
    _fails(db, bad)


def test_chunks_are_ordered_and_embedding_state_is_consistent(db, doc):
    v = version(doc, 1, current=True)
    db.add(v)
    db.commit()
    db.add(
        DocumentChunk(
            document_version_id=v.id, chunk_index=0, content="Texte", content_hash=sha("Texte")
        )
    )
    db.commit()
    _fails(
        db,
        DocumentChunk(
            document_version_id=v.id, chunk_index=0, content="dup", content_hash=sha("dup")
        ),
    )
    _fails(
        db,
        DocumentChunk(
            document_version_id=v.id,
            chunk_index=1,
            content="x",
            content_hash=sha("x"),
            embedded_at=NOW,
        ),
    )  # embedded without naming the model
    db.add(
        DocumentChunk(
            document_version_id=v.id,
            chunk_index=1,
            content="x",
            content_hash=sha("x"),
            embedding_model="test-model",
            embedded_at=NOW,
        )
    )
    db.commit()


def test_ingestion_job_rules(db, doc):
    v = version(doc, 1, current=True)
    db.add(v)
    db.commit()
    db.add(IngestionJob(document_id=doc.id, document_version_id=v.id, action="ADD"))
    db.commit()
    # No second active job for the same version and action (idempotent upload).
    _fails(
        db,
        IngestionJob(document_id=doc.id, document_version_id=v.id, action="ADD", status="RUNNING"),
    )
    job = db.scalar(select(IngestionJob))
    job.status = "FAILED"
    job.error_message = "parser error"
    job.attempts = 1
    db.commit()
    db.add(
        IngestionJob(document_id=doc.id, document_version_id=v.id, action="ADD")
    )  # retry is allowed
    db.commit()
    _fails(
        db,
        IngestionJob(
            document_id=doc.id, document_version_id=v.id, action="UPDATE", status="FAILED"
        ),
    )
    _fails(
        db,
        IngestionJob(
            document_id=doc.id,
            document_version_id=v.id,
            action="UPDATE",
            attempts=5,
            max_attempts=3,
        ),
    )
    _fails(db, IngestionJob(document_id=doc.id, action="ADD"))  # an active ADD must name a version
    db.add(IngestionJob(document_id=doc.id, action="DELETE"))  # a DELETE may not
    db.commit()


def test_deleting_a_version_removes_its_chunks_but_keeps_job_history(db, doc):
    v = version(doc, 1, current=True)
    db.add(v)
    db.commit()
    db.add(
        DocumentChunk(document_version_id=v.id, chunk_index=0, content="t", content_hash=sha("t"))
    )
    db.add(
        IngestionJob(document_id=doc.id, document_version_id=v.id, action="ADD", status="SUCCEEDED")
    )
    db.commit()
    db.delete(db.get(DocumentVersion, v.id))
    db.commit()
    assert db.scalar(select(DocumentChunk.id)) is None
    job = db.scalar(select(IngestionJob))
    assert job is not None and job.document_version_id is None
