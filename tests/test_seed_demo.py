"""T6: demonstration data seeding (fictitious, idempotent, removable, never official)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db import demo_data
from app.db.seed_demo import SeedError, academic_year_window, remove_demo, seed_demo
from app.models import (
    Institution,
    Program,
    ProgramAdmissionRule,
    ProgramCourse,
    ProgramPaymentTerm,
    ProgramSpecialization,
    ProgramTuition,
    StaffUser,
)
from app.schemas.catalogue_detail import (
    AdmissionCreate,
    CourseCreate,
    PaymentTermCreate,
    SpecializationCreate,
    TuitionCreate,
)
from app.schemas.program import ProgramCreate

PUBLIC = "/api/v1/programs"


@pytest.fixture
def db(client, test_engine):  # `client` cleans the tables and creates one real admin
    factory = sessionmaker(bind=test_engine, expire_on_commit=False)
    with factory() as session:
        yield session


def counts(db):
    return {
        m.__name__: db.scalar(select(func.count()).select_from(m))
        for m in (
            Program,
            ProgramSpecialization,
            ProgramCourse,
            ProgramAdmissionRule,
            ProgramTuition,
            ProgramPaymentTerm,
            StaffUser,
        )
    }


def public_items(client):
    return client.get(PUBLIC, params={"limit": 100}).json()["items"]


def test_refuses_to_create_staff_when_no_administrator_exists(db):
    db.query(StaffUser).delete()
    db.commit()
    with pytest.raises(SeedError):
        seed_demo(db)
    assert db.scalar(select(func.count()).select_from(StaffUser)) == 0  # bootstrap stays possible
    assert seed_demo(db, with_staff=False).created["programmes"] == len(demo_data.DEMO_PROGRAMS)


def test_default_run_creates_invisible_drafts_and_working_demo_accounts(client, db):
    report = seed_demo(db)
    assert report.created["programmes"] == 5
    assert public_items(client) == []  # drafts are never public
    assert len(report.generated_passwords) == 5
    for email, password in report.generated_passwords.items():
        login = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200, email
    iit_user = db.scalar(select(StaffUser).where(StaffUser.email == "demo.iit@example.org"))
    assert iit_user.role == "ACADEMIC_IIT" and iit_user.institution_id is not None


def test_generated_passwords_are_distinct_and_long(db):
    report = seed_demo(db)
    passwords = list(report.generated_passwords.values())
    assert len(set(passwords)) == 5 and all(len(p) >= 16 for p in passwords)


def test_shared_password_from_environment_variable(client, db):
    report = seed_demo(db, staff_password="Shared-Demo-Pass-123")
    assert set(report.generated_passwords.values()) == {None}  # nothing to print
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "demo.admin@example.org", "password": "Shared-Demo-Pass-123"},
        ).status_code
        == 200
    )


def test_idempotent(db):
    seed_demo(db)
    before = counts(db)
    second = seed_demo(db)
    assert counts(db) == before
    assert second.created == {} and second.generated_passwords == {}


def test_publish_makes_demo_data_visible_with_fictitious_source_and_hides_expired_tariff(
    client, db
):
    seed_demo(db, publish=True, with_staff=False)
    items = public_items(client)
    assert len(items) == 5
    assert all(p["code"].startswith("DEMO-") and p["title"].startswith("[DÉMO]") for p in items)
    assert all(p["official_source_url"] == demo_data.DEMO_SOURCE_URL for p in items)
    program = items[0]
    tuition = client.get(f"{PUBLIC}/{program['id']}/tuition").json()
    assert (
        len(tuition) == 1 and "précédente" not in tuition[0]["label"]
    )  # last year's tariff has expired
    assert len(client.get(f"{PUBLIC}/{program['id']}/payment-terms").json()) == 2
    assert len(client.get(f"{PUBLIC}/{program['id']}/admission-rules").json()) == 3
    assert client.get(f"{PUBLIC}/{program['id']}/courses").json()


def test_publishing_after_a_draft_run_publishes_existing_rows(client, db):
    seed_demo(db, with_staff=False)
    assert public_items(client) == []
    seed_demo(db, publish=True, with_staff=False)
    assert len(public_items(client)) == 5


def test_remove_deletes_demo_data_but_keeps_real_data(client, db):
    iit = db.scalar(select(Institution).where(Institution.code == "IIT")) or Institution(
        code="IIT", name="IIT"
    )
    db.add(iit)
    db.flush()
    real = Program(
        institution_id=iit.id,
        code="REAL-1",
        title="Vraie formation",
        level="LICENCE",
        status="DRAFT",
    )
    db.add(real)
    db.commit()
    seed_demo(db, publish=True)
    removed = remove_demo(db)
    assert removed["programmes"] == 5 and removed["comptes responsables"] == 5
    assert db.scalar(select(Program.code).where(Program.code == "REAL-1")) == "REAL-1"
    assert (
        db.scalar(select(func.count()).select_from(Program).where(Program.code.like("DEMO-%"))) == 0
    )
    assert db.scalar(select(StaffUser).where(StaffUser.email == "admin@example.org")) is not None
    assert remove_demo(db) == {
        "programmes": 0,
        "comptes responsables": 0,
        "programmes conservés": 0,
    }


def test_academic_year_window_never_expires_the_current_year():
    for month in range(1, 13):
        now = datetime(2026, month, 15, tzinfo=timezone.utc)
        w = academic_year_window(now)
        assert w["from"] <= now <= w["to"] and w["prev_to"] < now


def test_demo_data_passes_the_public_api_schemas():
    """Guards against demo content the real API would reject (pattern, ranges, lengths)."""
    window = academic_year_window(datetime(2026, 11, 22, tzinfo=timezone.utc))
    codes = set()
    for spec in demo_data.DEMO_PROGRAMS:
        assert spec["code"] not in codes
        codes.add(spec["code"])
        ProgramCreate(
            institution_id="00000000-0000-0000-0000-000000000001",
            code=spec["code"],
            title=spec["title"],
            level=spec["level"],
            duration_years=spec["duration_years"],
        )
        spec_codes = {c for c, _, _ in spec["specializations"]}
        for code, title, description in spec["specializations"]:
            SpecializationCreate(code=code, title=title, description=description)
        for code, title, semester, credits, spec_code in spec["courses"]:
            CourseCreate(code=code, title=title, semester=semester, credits=credits)
            assert spec_code is None or spec_code in spec_codes
        TuitionCreate(label="x1", amount=spec["tuition"], academic_year=window["label"])
    for kind, title, description in demo_data.rules():
        AdmissionCreate(kind=kind, title=title, description=description)
    PaymentTermCreate(
        label="x1",
        academic_year=window["label"],
        payment_mode="INSTALLMENTS",
        installments_count=3,
        first_payment_percent="40.00",
    )
