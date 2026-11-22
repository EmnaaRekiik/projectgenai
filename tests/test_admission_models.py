"""Database rules of the candidate request tables (migration 0008). Runs in SQLite or PostgreSQL."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.models import (
    Appointment, CandidateUser, EquivalenceRequest, InterviewResult, Institution, Preregistration, Program,
    StaffRole, StaffUser,
)

NOW = datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc)


@pytest.fixture
def db(client, test_engine):
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with factory() as session:
        yield session


@pytest.fixture
def base(db):
    inst = Institution(code="IIT", name="Test institute")
    db.add(inst)
    db.flush()
    program = Program(institution_id=inst.id, code="DEMO-1", title="Fictitious test programme",
                      level="LICENCE", status="DRAFT")
    candidate = CandidateUser(email="c@example.org", display_name="Candidate", password_hash="x",
                              is_active=True, failed_login_count=0)
    manager = StaffUser(email="m@example.org", display_name="Manager", password_hash="x",
                        role=StaffRole.INTERVIEW_MANAGER.value, is_active=True, failed_login_count=0)
    db.add_all([program, candidate, manager])
    db.commit()
    return {"program": program, "candidate": candidate, "manager": manager}


def _commit_fails(db, obj):
    db.add(obj)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_preregistration_draft_needs_no_consent_but_submission_does(db, base):
    draft = Preregistration(candidate_id=base["candidate"].id, program_id=base["program"].id, status="DRAFT")
    db.add(draft)
    db.commit()
    # Submitting without consent is refused by the database...
    draft.status = "SUBMITTED"
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    # ...and accepted once consent is recorded.
    draft.status = "SUBMITTED"
    draft.consent_given_at = NOW
    draft.submitted_at = NOW
    db.commit()


def test_invalid_statuses_are_rejected(db, base):
    _commit_fails(db, Preregistration(candidate_id=base["candidate"].id, program_id=base["program"].id,
                                      status="MAYBE", consent_given_at=NOW))
    _commit_fails(db, EquivalenceRequest(candidate_id=base["candidate"].id, origin_diploma="D",
                                         origin_institution="U", status="WHATEVER"))


def test_equivalence_requires_origin_fields(db, base):
    _commit_fails(db, EquivalenceRequest(candidate_id=base["candidate"].id, origin_institution="U",
                                         status="DRAFT"))


def test_appointment_must_end_after_start(db, base):
    _commit_fails(db, Appointment(candidate_id=base["candidate"].id, starts_at=NOW, ends_at=NOW,
                                  status="PROPOSED"))
    db.add(Appointment(candidate_id=base["candidate"].id, manager_id=base["manager"].id, starts_at=NOW,
                       ends_at=NOW + timedelta(minutes=30), status="PROPOSED"))
    db.commit()


def test_interview_result_rules(db, base):
    appt = Appointment(candidate_id=base["candidate"].id, starts_at=NOW, ends_at=NOW + timedelta(hours=1),
                       status="CONFIRMED")
    db.add(appt)
    db.commit()
    # A decision is only allowed once the result is recorded.
    _commit_fails(db, InterviewResult(appointment_id=appt.id, status="HELD", decision="ADMITTED"))
    _commit_fails(db, InterviewResult(appointment_id=appt.id, status="QCM_DONE", qcm_score=140))
    db.add(InterviewResult(appointment_id=appt.id, status="RESULT_RECORDED", qcm_score=72.5,
                           decision="WAITLIST", recorded_by=base["manager"].id, recorded_at=NOW))
    db.commit()
    # One interview result per appointment.
    _commit_fails(db, InterviewResult(appointment_id=appt.id, status="PLANNED"))


def test_deleting_candidate_removes_requests_but_programme_is_protected(db, base):
    pre = Preregistration(candidate_id=base["candidate"].id, program_id=base["program"].id,
                          status="DRAFT")
    db.add(pre)
    db.commit()
    pre_id = pre.id
    db.delete(base["program"])
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.delete(db.get(CandidateUser, base["candidate"].id))
    db.commit()
    assert db.scalar(select(Preregistration.id).where(Preregistration.id == pre_id)) is None
