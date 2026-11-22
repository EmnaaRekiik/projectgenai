"""T7: payment terms, publication status and validity period (public = verified + published + valid now)."""
from datetime import datetime, timedelta, timezone

import pytest

ADMIN = "/api/v1/admin/programs"
PUBLIC = "/api/v1/programs"
DAY = timedelta(days=1)


def now():
    return datetime.now(timezone.utc)


def source():
    return {"official_source_url": "https://iit.example.edu/official-fees",
            "verified_at": (now() - timedelta(minutes=1)).isoformat()}


KINDS = {
    "tuition": {"label": "Annual fee", "amount": "1200.00", "academic_year": "2026-2027"},
    "admission-rules": {"kind": "ADMISSION", "title": "Entry rule", "description": "Baccalaureat required"},
    "payment-terms": {"label": "Three instalments", "academic_year": "2026-2027",
                      "payment_mode": "INSTALLMENTS", "installments_count": 3, "first_payment_percent": "40.00"},
}
ALL = list(KINDS)


@pytest.fixture
def published(client, headers, draft):
    response = client.patch(f"{ADMIN}/{draft['id']}", headers=headers, json={"status": "PUBLISHED", **source()})
    assert response.status_code == 200, response.text
    return draft


def create(client, headers, program, kind, **extra):
    return client.post(f"{ADMIN}/{program['id']}/{kind}", headers=headers, json={**KINDS[kind], **extra})


def public(client, program, kind):
    return client.get(f"{PUBLIC}/{program['id']}/{kind}")


# ---------- payment terms basics ----------

def test_payment_term_lifecycle_and_defaults(client, headers, published):
    created = create(client, headers, published, "payment-terms")
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["publication_status"] == "PUBLISHED"
    assert body["valid_from"] is None and body["valid_to"] is None
    assert body["installments_count"] == 3 and body["first_payment_percent"] == "40.00"
    assert public(client, published, "payment-terms").json() == []          # not verified yet
    url = f"{ADMIN}/{published['id']}/payment-terms/{body['id']}"
    assert client.patch(url, headers=headers, json=source()).status_code == 200
    assert len(public(client, published, "payment-terms").json()) == 1
    assert client.delete(url, headers=headers).status_code == 204


def test_full_payment_term(client, headers, published):
    created = client.post(f"{ADMIN}/{published['id']}/payment-terms", headers=headers, json={
        "label": "Pay once", "academic_year": "2026-2027", "payment_mode": "FULL"})
    assert created.status_code == 201, created.text
    assert created.json()["installments_count"] is None


@pytest.mark.parametrize("payload", [
    {"payment_mode": "FULL", "installments_count": 2},                 # count with FULL
    {"payment_mode": "INSTALLMENTS"},                                   # missing count
    {"payment_mode": "INSTALLMENTS", "installments_count": 1},
    {"payment_mode": "INSTALLMENTS", "installments_count": 13},
    {"payment_mode": "INSTALLMENTS", "installments_count": 3, "first_payment_percent": "0"},
    {"payment_mode": "INSTALLMENTS", "installments_count": 3, "first_payment_percent": "100.5"},
    {"payment_mode": "CASH"},                                          # unknown mode
    {"payment_mode": "FULL", "academic_year": "2026-2028"},             # not consecutive
])
def test_payment_term_validation_errors(client, headers, draft, payload):
    body = {"label": "Invalid", "academic_year": "2026-2027", **payload}
    assert client.post(f"{ADMIN}/{draft['id']}/payment-terms", headers=headers, json=body).status_code == 422


def test_payment_term_label_unique_per_year(client, headers, draft):
    assert create(client, headers, draft, "payment-terms").status_code == 201
    assert create(client, headers, draft, "payment-terms").status_code == 409


def test_patch_cannot_make_payment_term_inconsistent(client, headers, draft):
    item = client.post(f"{ADMIN}/{draft['id']}/payment-terms", headers=headers, json={
        "label": "Pay once", "academic_year": "2026-2027", "payment_mode": "FULL"}).json()
    url = f"{ADMIN}/{draft['id']}/payment-terms/{item['id']}"
    assert client.patch(url, headers=headers, json={"payment_mode": "INSTALLMENTS"}).status_code == 422
    ok = client.patch(url, headers=headers, json={"payment_mode": "INSTALLMENTS", "installments_count": 4})
    assert ok.status_code == 200, ok.text
    assert client.patch(url, headers=headers, json={"payment_mode": "FULL"}).status_code == 422
    assert client.patch(url, headers=headers, json={"payment_mode": None}).status_code == 422


# ---------- validity period ----------

@pytest.mark.parametrize("kind", ALL)
def test_validity_window_controls_public_visibility(client, headers, published, kind):
    url = f"{ADMIN}/{published['id']}/{kind}"
    item = create(client, headers, published, kind, **source(), valid_from=(now() - DAY).isoformat(),
                  valid_to=(now() + DAY).isoformat())
    assert item.status_code == 201, item.text
    assert len(public(client, published, kind).json()) == 1                  # inside the window
    item_id = item.json()["id"]
    # expired
    r = client.patch(f"{url}/{item_id}", headers=headers, json={
        "valid_from": (now() - 3 * DAY).isoformat(), "valid_to": (now() - DAY).isoformat(), **source()})
    assert r.status_code == 200, r.text
    assert public(client, published, kind).json() == []
    # not started yet
    r = client.patch(f"{url}/{item_id}", headers=headers, json={
        "valid_from": (now() + DAY).isoformat(), "valid_to": (now() + 3 * DAY).isoformat(), **source()})
    assert r.status_code == 200, r.text
    assert public(client, published, kind).json() == []
    # open-ended bounds mean unlimited
    r = client.patch(f"{url}/{item_id}", headers=headers, json={"valid_from": None, "valid_to": None, **source()})
    assert r.status_code == 200, r.text
    assert len(public(client, published, kind).json()) == 1
    # admins always see everything, whatever the period
    assert len(client.get(url, headers=headers).json()) == 1


@pytest.mark.parametrize("kind", ALL)
@pytest.mark.parametrize("status", ["DRAFT", "ARCHIVED"])
def test_publication_status_hides_verified_items(client, headers, published, kind, status):
    item = create(client, headers, published, kind, **source()).json()
    url = f"{ADMIN}/{published['id']}/{kind}/{item['id']}"
    assert len(public(client, published, kind).json()) == 1
    hidden = client.patch(url, headers=headers, json={"publication_status": status})
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["verified_at"] is not None          # a management change keeps the evidence
    assert public(client, published, kind).json() == []
    back = client.patch(url, headers=headers, json={"publication_status": "PUBLISHED"})
    assert back.status_code == 200
    assert len(public(client, published, kind).json()) == 1
    assert client.patch(url, headers=headers, json={"publication_status": None}).status_code == 422
    assert client.patch(url, headers=headers, json={"publication_status": "LIVE"}).status_code == 422


@pytest.mark.parametrize("kind", ALL)
def test_changing_validity_requires_new_verification(client, headers, published, kind):
    item = create(client, headers, published, kind, **source()).json()
    url = f"{ADMIN}/{published['id']}/{kind}/{item['id']}"
    changed = client.patch(url, headers=headers, json={"valid_to": (now() + 30 * DAY).isoformat()})
    assert changed.status_code == 200, changed.text
    assert changed.json()["verified_at"] is None
    assert public(client, published, kind).json() == []


@pytest.mark.parametrize("kind", ALL)
def test_invalid_validity_periods_are_rejected(client, headers, draft, kind):
    start = now()
    base = f"{ADMIN}/{draft['id']}/{kind}"
    for extra in ({"valid_from": start.isoformat(), "valid_to": start.isoformat()},
                  {"valid_from": start.isoformat(), "valid_to": (start - DAY).isoformat()},
                  {"valid_from": "2026-09-01T00:00:00"}):         # no timezone: ambiguous, refused
        assert create(client, headers, draft, kind, **extra).status_code == 422, extra
    item = create(client, headers, draft, kind, valid_from=start.isoformat()).json()
    # patching only valid_to must be compared with the stored valid_from
    assert client.patch(f"{base}/{item['id']}", headers=headers,
                        json={"valid_to": (start - DAY).isoformat()}).status_code == 422


def test_validity_offsets_are_normalised_to_utc(client, headers, published):
    # Wall-clock 00:30 at UTC+1 is 23:30 UTC the previous day; the API stores and returns UTC.
    day = now() + 2 * DAY
    local = datetime(day.year, day.month, day.day, 0, 30, tzinfo=timezone(timedelta(hours=1)))
    item = create(client, headers, published, "tuition", **source(), valid_from=local.isoformat())
    assert item.status_code == 201, item.text
    expected = local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    assert item.json()["valid_from"].startswith(expected)
    assert public(client, published, "tuition").json() == []     # starts in the future


# ---------- access ----------

@pytest.mark.parametrize("kind", ALL)
def test_anonymous_cannot_write_and_unpublished_programme_is_hidden(client, headers, draft, kind):
    assert client.post(f"{ADMIN}/{draft['id']}/{kind}", json=KINDS[kind]).status_code == 401
    assert create(client, headers, draft, kind, **source()).status_code == 201
    assert public(client, draft, kind).status_code == 404       # programme still DRAFT


def test_other_institution_staff_cannot_manage_payment_terms(client, test_engine, headers, draft):
    from sqlalchemy.orm import Session
    from app.auth.passwords import hash_password
    from app.auth.tokens import digest_token
    from app.models import Institution, StaffRole, StaffSession, StaffUser
    with Session(test_engine) as db:
        isb = Institution(code="ISB", name="ISB test")
        db.add(isb)
        db.flush()
        user = StaffUser(email="isb@example.org", display_name="ISB", password_hash=hash_password("ExampleSecurePass123!"),
                         role=StaffRole.ACADEMIC_ISB.value, institution_id=isb.id, failed_login_count=0, is_active=True)
        db.add(user)
        db.flush()
        db.add(StaffSession(user_id=user.id, token_hash=digest_token("isb-test-token"),
                            expires_at=now() + timedelta(hours=12)))
        db.commit()
    other = {"Authorization": "Bearer isb-test-token"}
    response = client.post(f"{ADMIN}/{draft['id']}/payment-terms", headers=other, json=KINDS["payment-terms"])
    assert response.status_code == 404                           # an IIT programme is invisible to ISB staff
    assert client.get(f"{ADMIN}/{draft['id']}/payment-terms", headers=other).status_code == 404
