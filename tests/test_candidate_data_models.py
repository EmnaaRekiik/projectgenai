"""Rules of the academic profile and candidate-owned conversation tables (migration 0009)."""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import (
    AcademicProfile, CandidateConversation, CandidateMessage, CandidateUser, Institution, Preregistration, Program,
)

NOW = datetime(2026, 11, 22, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(client, test_engine):
    with sessionmaker(bind=test_engine, expire_on_commit=False)() as session:
        yield session


@pytest.fixture
def candidate(db):
    c = CandidateUser(email="p@example.org", display_name="Profile", password_hash="x", is_active=True,
                      failed_login_count=0)
    db.add(c)
    db.commit()
    return c


def _fails(db, obj):
    db.add(obj)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_one_profile_per_candidate_and_grade_range(db, candidate):
    db.add(AcademicProfile(candidate_id=candidate.id, bac_series="Sciences", bac_year=2026,
                           average_grade=14.5, preferred_language="arabizi", source="AGENT"))
    db.commit()
    _fails(db, AcademicProfile(candidate_id=candidate.id, source="CANDIDATE"))


@pytest.mark.parametrize("field,value", [("average_grade", 21), ("average_grade", -1), ("bac_year", 1800),
                                         ("preferred_language", "klingon"), ("source", "ROBOT")])
def test_profile_invalid_values_rejected(db, candidate, field, value):
    values = {"candidate_id": candidate.id, "source": "CANDIDATE"}
    values[field] = value
    _fails(db, AcademicProfile(**values))


def test_claimed_conversation_needs_consent_and_cannot_be_claimed_twice(db, candidate):
    session_id = uuid.uuid4()
    # Claimed from a visitor session without consent is refused by the database.
    _fails(db, CandidateConversation(candidate_id=candidate.id, source_visitor_session_id=session_id))
    db.add(CandidateConversation(candidate_id=candidate.id, source_visitor_session_id=session_id,
                                 consent_given_at=NOW, claimed_at=NOW))
    db.commit()
    other = CandidateUser(email="o@example.org", display_name="Other", password_hash="x", is_active=True,
                          failed_login_count=0)
    db.add(other)
    db.commit()
    # The same visitor session cannot end up in two accounts (or twice in one).
    _fails(db, CandidateConversation(candidate_id=other.id, source_visitor_session_id=session_id,
                                     consent_given_at=NOW))
    # A conversation started directly by the candidate has no source session and needs no claim consent.
    db.add(CandidateConversation(candidate_id=candidate.id))
    db.add(CandidateConversation(candidate_id=candidate.id))
    db.commit()


def test_messages_are_ordered_unique_and_deleted_with_candidate(db, candidate):
    conv = CandidateConversation(candidate_id=candidate.id)
    db.add(conv)
    db.commit()
    db.add_all([CandidateMessage(conversation_id=conv.id, sequence=1, role="user", content="Salam", detected_language="derja"),
                CandidateMessage(conversation_id=conv.id, sequence=2, role="assistant", content="Bonjour")])
    db.commit()
    _fails(db, CandidateMessage(conversation_id=conv.id, sequence=2, role="user", content="dup"))
    _fails(db, CandidateMessage(conversation_id=conv.id, sequence=3, role="system", content="bad role"))
    _fails(db, CandidateMessage(conversation_id=conv.id, sequence=0, role="user", content="bad seq"))
    conv_id = conv.id
    db.delete(db.get(CandidateUser, candidate.id))
    db.commit()
    assert db.scalar(select(CandidateMessage.id).where(CandidateMessage.conversation_id == conv_id)) is None


def test_only_one_active_preregistration_per_candidate_and_programme(db, candidate):
    inst = Institution(code="IIT", name="Institute")
    db.add(inst)
    db.flush()
    prog = Program(institution_id=inst.id, code="P1", title="Fictitious programme", level="LICENCE", status="DRAFT")
    db.add(prog)
    db.commit()

    def pre(status):
        return Preregistration(candidate_id=candidate.id, program_id=prog.id, status=status,
                               consent_given_at=NOW, submitted_at=NOW)

    db.add(pre("SUBMITTED"))
    db.commit()
    _fails(db, pre("COMPLETE"))  # second active application for the same programme
    # A cancelled or rejected one does not block a new application.
    first = db.scalar(select(Preregistration))
    first.status = "CANCELLED"
    db.commit()
    db.add(pre("SUBMITTED"))
    db.commit()
