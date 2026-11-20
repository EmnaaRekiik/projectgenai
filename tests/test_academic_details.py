"""Functional public/admin contracts for academic facts with source evidence."""
from datetime import datetime, timedelta, timezone

import pytest


ADMIN = "/api/v1/admin/programs"
PUBLIC = "/api/v1/programs"


def source():
    return {"official_source_url": "https://iit.example.edu/official-catalogue",
            "verified_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}


@pytest.mark.parametrize("endpoint,data,field", [
    ("specializations", {"code": "DS", "title": "Data Science"}, "title"),
    ("courses", {"code": "ALGO", "title": "Algorithmique", "semester": 1, "credits": 6}, "title"),
    ("admission-rules", {"kind": "PREREQUISITE", "title": "Prerequisite", "description": "Baccalaureat"}, "title"),
    ("tuition", {"label": "Annual fee", "amount": "1200.00", "currency": "TND", "academic_year": "2026-2027"}, "label"),
])
def test_details_only_public_if_program_and_row_verified(client, headers, draft, endpoint, data, field):
    url = f"{ADMIN}/{draft['id']}/{endpoint}"
    created = client.post(url, headers=headers, json=data)
    assert created.status_code == 201, created.text
    id = created.json()["id"]
    assert created.json()[field] == data[field]
    assert len(client.get(url, headers=headers).json()) == 1
    public = f"{PUBLIC}/{draft['id']}/{endpoint}"
    assert client.get(public).status_code == 404
    # Publishing the programme doesn't automatically publish unverified detail facts.
    published = client.patch(f"{ADMIN}/{draft['id']}", headers=headers,
                             json={"status": "PUBLISHED", **source()})
    assert published.status_code == 200, published.text
    assert client.get(public).json() == []
    verified = client.patch(f"{url}/{id}", headers=headers, json=source())
    assert verified.status_code == 200, verified.text
    assert len(client.get(public).json()) == 1
    # Any substantive edit makes verified info private until new evidence is supplied.
    edited = client.patch(f"{url}/{id}", headers=headers, json={field: "Changed title"})
    assert edited.status_code == 200, edited.text
    assert edited.json()["verified_at"] is None
    assert client.get(public).json() == []
    assert client.delete(f"{url}/{id}", headers=headers).status_code == 204
    assert client.get(url, headers=headers).json() == []


@pytest.mark.parametrize("endpoint,payload", [
    ("specializations", {"code": "DATA", "title": "Data Science"}),
    ("courses", {"code": "MATH", "title": "Maths", "semester": 1}),
    ("admission-rules", {"kind": "DOCUMENT", "title": "Required document", "description": "Bac transcript"}),
    ("tuition", {"label": "Annual", "amount": "0.00", "academic_year": "2026-2027"}),
])
def test_student_or_anonymous_cannot_write_catalogue(client, draft, endpoint, payload):
    response = client.post(f"{ADMIN}/{draft['id']}/{endpoint}", json=payload)
    assert response.status_code == 401


def test_verified_requires_https_source_and_past_timestamp(client, headers, draft):
    url = f"{ADMIN}/{draft['id']}/tuition"
    item = {"label": "Fee", "amount": "100", "academic_year": "2026-2027"}
    bad = client.post(url, headers=headers, json={**item,
        "official_source_url": "http://example.com", "verified_at": datetime.now(timezone.utc).isoformat()})
    assert bad.status_code == 422, bad.text
    future = client.post(url, headers=headers, json={**item,
        "official_source_url": "https://example.com", "verified_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
    assert future.status_code == 422, future.text


def test_specialization_codes_are_unique_per_program(client, headers, draft):
    url = f"{ADMIN}/{draft['id']}/specializations"
    payload = {"code": "DS", "title": "Data Science"}
    assert client.post(url, json=payload, headers=headers).status_code == 201
    assert client.post(url, json=payload, headers=headers).status_code == 409


def test_detail_cannot_be_read_or_changed_under_another_program(client, headers, draft, institution):
    created = client.post(f"{ADMIN}/{draft['id']}/courses", headers=headers,
                          json={"code": "PY1", "title": "Python", "semester": 1}).json()
    other = client.post(ADMIN, headers=headers, json={
        "institution_id": institution["id"], "code": "OTHER", "title": "Other course",
        "level": "LICENCE"}).json()
    assert client.patch(f"{ADMIN}/{other['id']}/courses/{created['id']}",
                        headers=headers, json={"title": "Hacked"}).status_code == 404
    assert client.delete(f"{ADMIN}/{other['id']}/courses/{created['id']}",
                         headers=headers).status_code == 404


def test_tuition_requires_two_consecutive_years(client, headers, draft):
    response = client.post(f"{ADMIN}/{draft['id']}/tuition", headers=headers, json={
        "label": "Annual", "amount": "500", "academic_year": "2026-2029"})
    assert response.status_code == 422


def test_patch_invalid_required_field(client, headers, draft):
    item = client.post(f"{ADMIN}/{draft['id']}/courses", headers=headers,
                       json={"code": "ALG", "title": "Algorithmes", "semester": 2}).json()
    assert client.patch(f"{ADMIN}/{draft['id']}/courses/{item['id']}",
                        headers=headers, json={"semester": None}).status_code == 422


def test_course_specialization_must_belong_to_same_program(client, headers, draft, institution):
    created = client.post(f"{ADMIN}/{draft['id']}/specializations", headers=headers,
                          json={"code": "AI", "title": "Artificial Intelligence"})
    assert created.status_code == 201
    spec = created.json()
    linked = client.post(f"{ADMIN}/{draft['id']}/courses", headers=headers,
                         json={"code": "DEEP", "title": "Deep Learning", "semester": 3,
                               "specialization_id": spec["id"]})
    assert linked.status_code == 201, linked.text
    assert linked.json()["specialization_id"] == spec["id"]
    # FK enforcement is checked on PostgreSQL; SQLite tests run with PRAGMA foreign_keys=ON.
    other = client.post(ADMIN, headers=headers, json={"institution_id": institution["id"],
        "code": "OTHER2", "title": "Second programme", "level": "LICENCE"}).json()
    bad = client.post(f"{ADMIN}/{other['id']}/courses", headers=headers,
                      json={"code": "DEEP", "title": "Deep Learning", "semester": 3,
                            "specialization_id": spec["id"]})
    assert bad.status_code == 409, bad.text


def test_direction_can_read_but_not_edit_program(client, test_engine, draft):
    from sqlalchemy.orm import Session
    from app.models.staff import StaffUser, StaffSession, StaffRole
    from app.auth.passwords import hash_password
    from app.auth.tokens import digest_token
    with Session(test_engine) as db:
        user = StaffUser(email="direction@example.org", display_name="Direction",
            password_hash=hash_password("ExampleSecurePass123!"), role=StaffRole.DIRECTION.value,
            failed_login_count=0, is_active=True)
        db.add(user)
        db.flush()
        db.add(StaffSession(user_id=user.id, token_hash=digest_token("direction-test-token"),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=12)))
        db.commit()
    header = {"Authorization": "Bearer direction-test-token"}
    assert client.get(f"{ADMIN}/{draft['id']}", headers=header).status_code == 200
    assert client.patch(f"{ADMIN}/{draft['id']}", headers=header,
                        json={"title": "Cannot edit"}).status_code == 403
