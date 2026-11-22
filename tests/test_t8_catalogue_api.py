"""T8: end-to-end tests of the tuition / payment-terms / admission-rules APIs.

Covers what the unit-level tests do not: access control per role and per institution, the full
staff-to-public workflow, pagination, and the interaction between programme status, publication
status, verification and validity period.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password
from app.auth.tokens import digest_token
from app.models import StaffRole, StaffSession, StaffUser

ADMIN = "/api/v1/admin/programs"
PUBLIC = "/api/v1/programs"
RESOURCES = {
    "tuition": {"label": "Annual fee", "amount": "1500.00", "academic_year": "2026-2027"},
    "payment-terms": {
        "label": "Three instalments",
        "academic_year": "2026-2027",
        "payment_mode": "INSTALLMENTS",
        "installments_count": 3,
        "first_payment_percent": "40.00",
    },
    "admission-rules": {
        "kind": "ADMISSION",
        "title": "Entry rule",
        "description": "Baccalaureat required",
    },
}


def evidence():
    return {
        "official_source_url": "https://iit.example.edu/official",
        "verified_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    }


def staff_headers(test_engine, email, role, institution_id=None):
    token = f"token-{email}"
    with Session(test_engine) as db:
        user = StaffUser(
            email=email,
            display_name=email,
            password_hash=hash_password("ExampleSecurePass123!"),
            role=role.value,
            institution_id=uuid.UUID(institution_id) if institution_id else None,
            is_active=True,
            failed_login_count=0,
        )
        db.add(user)
        db.flush()
        db.add(
            StaffSession(
                user_id=user.id,
                token_hash=digest_token(token),
                expires_at=datetime.now(timezone.utc) + timedelta(hours=12),
            )
        )
        db.commit()
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def world(client, test_engine, headers, institution):
    """Two institutions, a published IIT programme, an ISB draft programme, and one staff user per role."""
    isb = client.post(
        "/api/v1/institutions",
        json={"code": "ISB", "name": "Institut Supérieur de Business"},
        headers=headers,
    ).json()
    iit_program = client.post(
        ADMIN,
        headers=headers,
        json={
            "institution_id": institution["id"],
            "code": "T8-IIT",
            "title": "Programme IIT T8",
            "level": "LICENCE",
        },
    ).json()
    assert (
        client.patch(
            f"{ADMIN}/{iit_program['id']}",
            headers=headers,
            json={"status": "PUBLISHED", **evidence()},
        ).status_code
        == 200
    )
    isb_program = client.post(
        ADMIN,
        headers=headers,
        json={
            "institution_id": isb["id"],
            "code": "T8-ISB",
            "title": "Programme ISB T8",
            "level": "LICENCE",
        },
    ).json()
    return {
        "iit_program": iit_program,
        "isb_program": isb_program,
        "iit": staff_headers(
            test_engine, "t8-iit@example.org", StaffRole.ACADEMIC_IIT, institution["id"]
        ),
        "isb": staff_headers(test_engine, "t8-isb@example.org", StaffRole.ACADEMIC_ISB, isb["id"]),
        "direction": staff_headers(test_engine, "t8-dir@example.org", StaffRole.DIRECTION),
        "interview": staff_headers(test_engine, "t8-int@example.org", StaffRole.INTERVIEW_MANAGER),
    }


def post(client, program, kind, who, **extra):
    return client.post(
        f"{ADMIN}/{program['id']}/{kind}", headers=who, json={**RESOURCES[kind], **extra}
    )


# ---------- complete workflow: staff writes, public reads ----------


@pytest.mark.parametrize("kind", RESOURCES)
def test_full_workflow_draft_verify_public_edit_unverify_delete(client, world, kind):
    program, iit = world["iit_program"], world["iit"]
    created = post(client, program, kind, iit)
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]
    url = f"{ADMIN}/{program['id']}/{kind}/{item_id}"
    public_url = f"{PUBLIC}/{program['id']}/{kind}"

    assert client.get(public_url).json() == []  # unverified: hidden
    assert (
        len(client.get(f"{ADMIN}/{program['id']}/{kind}", headers=iit).json()) == 1
    )  # staff still sees it
    assert client.patch(url, headers=iit, json=evidence()).status_code == 200
    assert len(client.get(public_url).json()) == 1  # verified: visible

    content_change = (
        {"description": "Updated"} if kind == "admission-rules" else {"label": "Updated label"}
    )
    edited = client.patch(url, headers=iit, json=content_change)
    assert edited.status_code == 200, edited.text
    assert edited.json()["verified_at"] is None
    assert client.get(public_url).json() == []  # edit withdrew verification

    assert client.patch(url, headers=iit, json=evidence()).status_code == 200
    assert (
        client.patch(url, headers=iit, json={"publication_status": "ARCHIVED"}).status_code == 200
    )
    assert client.get(public_url).json() == []  # archived: hidden
    assert (
        client.patch(url, headers=iit, json={"publication_status": "PUBLISHED"}).status_code == 200
    )
    assert len(client.get(public_url).json()) == 1  # status change keeps evidence

    assert client.delete(url, headers=iit).status_code == 204
    assert client.delete(url, headers=iit).status_code == 404
    assert client.get(public_url).json() == []


# ---------- access control ----------


@pytest.mark.parametrize("kind", RESOURCES)
def test_anonymous_and_invalid_tokens_are_rejected_on_staff_routes(client, world, kind):
    base = f"{ADMIN}/{world['iit_program']['id']}/{kind}"
    for headers in ({}, {"Authorization": "Bearer not-a-real-token-0000000000000000"}):
        assert client.get(base, headers=headers).status_code == 401
        assert client.post(base, headers=headers, json=RESOURCES[kind]).status_code == 401


@pytest.mark.parametrize("kind", RESOURCES)
def test_direction_reads_but_cannot_write(client, world, kind):
    program, iit, direction = world["iit_program"], world["iit"], world["direction"]
    item_id = post(client, program, kind, iit).json()["id"]
    base = f"{ADMIN}/{program['id']}/{kind}"
    assert client.get(base, headers=direction).status_code == 200
    assert post(client, program, kind, direction).status_code == 403
    assert client.patch(f"{base}/{item_id}", headers=direction, json=evidence()).status_code == 403
    assert client.delete(f"{base}/{item_id}", headers=direction).status_code == 403


@pytest.mark.parametrize("kind", RESOURCES)
def test_interview_manager_has_no_catalogue_write_access(client, world, kind):
    assert post(client, world["iit_program"], kind, world["interview"]).status_code == 403


@pytest.mark.parametrize("kind", RESOURCES)
def test_academic_staff_cannot_touch_another_institution(client, world, kind):
    isb_program, iit, isb = world["isb_program"], world["iit"], world["isb"]
    item_id = post(client, isb_program, kind, isb).json()["id"]
    base = f"{ADMIN}/{isb_program['id']}/{kind}"
    assert client.get(base, headers=iit).status_code == 404
    assert post(client, isb_program, kind, iit).status_code == 404
    assert client.patch(f"{base}/{item_id}", headers=iit, json=evidence()).status_code == 404
    assert client.delete(f"{base}/{item_id}", headers=iit).status_code == 404
    assert client.get(base, headers=isb).status_code == 200  # owner is unaffected


@pytest.mark.parametrize("kind", RESOURCES)
def test_platform_admin_can_manage_any_institution(client, world, headers, kind):
    assert post(client, world["isb_program"], kind, headers).status_code == 201
    assert post(client, world["iit_program"], kind, headers).status_code == 201


# ---------- programme status gates the public view ----------


@pytest.mark.parametrize("kind", RESOURCES)
def test_draft_programme_exposes_nothing_even_with_verified_items(client, world, headers, kind):
    program = world["isb_program"]
    item_id = post(client, program, kind, headers).json()["id"]
    assert (
        client.patch(
            f"{ADMIN}/{program['id']}/{kind}/{item_id}", headers=headers, json=evidence()
        ).status_code
        == 200
    )
    assert client.get(f"{PUBLIC}/{program['id']}/{kind}").status_code == 404


@pytest.mark.parametrize("kind", RESOURCES)
def test_archiving_the_programme_withdraws_its_details(client, world, headers, kind):
    program = world["iit_program"]
    item_id = post(client, program, kind, headers).json()["id"]
    assert (
        client.patch(
            f"{ADMIN}/{program['id']}/{kind}/{item_id}", headers=headers, json=evidence()
        ).status_code
        == 200
    )
    assert len(client.get(f"{PUBLIC}/{program['id']}/{kind}").json()) == 1
    assert (
        client.patch(
            f"{ADMIN}/{program['id']}", headers=headers, json={"status": "ARCHIVED"}
        ).status_code
        == 200
    )
    assert client.get(f"{PUBLIC}/{program['id']}/{kind}").status_code == 404


# ---------- input and error handling ----------


@pytest.mark.parametrize("kind", RESOURCES)
def test_unknown_program_and_malformed_ids(client, headers, kind):
    unknown = "00000000-0000-0000-0000-000000000099"
    assert client.get(f"{PUBLIC}/{unknown}/{kind}").status_code == 404
    assert client.get(f"{ADMIN}/{unknown}/{kind}", headers=headers).status_code == 404
    assert client.get(f"{PUBLIC}/not-a-uuid/{kind}").status_code == 422
    assert (
        client.patch(f"{ADMIN}/{unknown}/{kind}/{unknown}", headers=headers, json={}).status_code
        == 404
    )


@pytest.mark.parametrize("kind", RESOURCES)
def test_unknown_fields_and_empty_body_are_rejected(client, world, headers, kind):
    program = world["iit_program"]
    assert post(client, program, kind, headers, surprise="x").status_code == 422
    assert (
        client.post(f"{ADMIN}/{program['id']}/{kind}", headers=headers, json={}).status_code == 422
    )


@pytest.mark.parametrize("kind", RESOURCES)
def test_validity_window_must_be_ordered_and_timezone_aware(client, world, headers, kind):
    program, now = world["iit_program"], datetime.now(timezone.utc)
    reversed_window = {
        "valid_from": now.isoformat(),
        "valid_to": (now - timedelta(days=1)).isoformat(),
    }
    assert post(client, program, kind, headers, **reversed_window).status_code == 422
    assert (
        post(client, program, kind, headers, valid_from="2026-09-01T00:00:00").status_code == 422
    )  # naive datetime
    assert post(client, program, kind, headers, publication_status="DELETED").status_code == 422


def test_amount_validation(client, world, headers):
    program = world["iit_program"]
    for amount in ("-1", "abc", "12.345", "1" + "0" * 12):
        assert post(client, program, "tuition", headers, amount=amount).status_code == 422, amount
    assert (
        post(client, program, "tuition", headers, amount="0").status_code == 201
    )  # free of charge is legal


def test_duplicate_tuition_returns_409_and_does_not_poison_the_session(client, world, headers):
    program = world["iit_program"]
    assert post(client, program, "tuition", headers).status_code == 201
    assert post(client, program, "tuition", headers).status_code == 409
    assert post(client, program, "tuition", headers, label="Other label").status_code == 201


# ---------- pagination ----------


@pytest.mark.parametrize("kind", ["tuition", "admission-rules"])
def test_public_pagination(client, world, headers, kind):
    program = world["iit_program"]
    for number in range(5):
        field = {"label": f"Fee {number}"} if kind == "tuition" else {"title": f"Rule {number}"}
        item_id = post(client, program, kind, headers, **field).json()["id"]
        client.patch(f"{ADMIN}/{program['id']}/{kind}/{item_id}", headers=headers, json=evidence())
    url = f"{PUBLIC}/{program['id']}/{kind}"
    first = client.get(url, params={"limit": 2, "offset": 0}).json()
    second = client.get(url, params={"limit": 2, "offset": 2}).json()
    last = client.get(url, params={"limit": 2, "offset": 4}).json()
    assert [len(first), len(second), len(last)] == [2, 2, 1]
    assert len({row["id"] for row in first + second + last}) == 5  # no duplicates, no gaps
    for bad in ({"limit": 0}, {"limit": 101}, {"offset": -1}):
        assert client.get(url, params=bad).status_code == 422


# ---------- cross-resource scenario used for the demo ----------


def test_candidate_view_of_a_complete_programme(client, world, headers):
    """What the chatbot/frontend reads for one programme: fees, payment terms and admission conditions."""
    program = world["iit_program"]
    for kind in RESOURCES:
        item = post(client, program, kind, headers).json()
        assert (
            client.patch(
                f"{ADMIN}/{program['id']}/{kind}/{item['id']}", headers=headers, json=evidence()
            ).status_code
            == 200
        )
    view = {kind: client.get(f"{PUBLIC}/{program['id']}/{kind}").json() for kind in RESOURCES}
    assert view["tuition"][0]["amount"] == "1500.00" and view["tuition"][0]["currency"] == "TND"
    assert view["payment-terms"][0]["installments_count"] == 3
    assert view["admission-rules"][0]["kind"] == "ADMISSION"
    for rows in view.values():
        assert rows[0]["official_source_url"].startswith("https://") and rows[0]["verified_at"]
