"""SA-28: authentication, permissions and revocable tokens."""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import check_password
from app.auth.tokens import digest_token
from app.models import StaffSession, StaffUser
from tests.conftest import TEST_KEY, TEST_TOKEN

BASE = "/api/v1"
PASS = "TestOnly-StrongPass_987654321"


def admin_headers():
    return {"Authorization": f"Bearer {TEST_TOKEN}"}


def login(client, email="admin@example.org", password=PASS):
    return client.post(f"{BASE}/auth/login", json={"email": email, "password": password})


def new_staff(client, *, role, email, institution_id=None):
    payload = {
        "email": email,
        "display_name": "Test Member",
        "password": PASS,
        "role": role,
        "institution_id": institution_id,
    }
    return client.post(f"{BASE}/staff", json=payload, headers=admin_headers())


def headers_for(client, email):
    answer = login(client, email)
    assert answer.status_code == 200, answer.text
    return {"Authorization": f"Bearer {answer.json()['access_token']}"}


def test_bootstrap_is_one_time_and_key_protected(client, test_engine):
    data = {
        "email": "first@example.org",
        "display_name": "First Admin",
        "password": PASS,
        "role": "PLATFORM_ADMIN",
    }
    assert client.post(f"{BASE}/auth/bootstrap", json=data).status_code == 401
    assert (
        client.post(
            f"{BASE}/auth/bootstrap", json=data, headers={"X-Admin-Key": TEST_KEY}
        ).status_code
        == 409
    )
    # Delete test admin to reproduce a truly empty installation.
    with Session(test_engine) as db:
        db.query(StaffSession).delete()
        db.query(StaffUser).delete()
        db.commit()
    bad = client.post(
        f"{BASE}/auth/bootstrap",
        json={**data, "role": "ACADEMIC_IIT"},
        headers={"X-Admin-Key": TEST_KEY},
    )
    assert bad.status_code == 422
    created = client.post(f"{BASE}/auth/bootstrap", json=data, headers={"X-Admin-Key": TEST_KEY})
    assert created.status_code == 201, created.text
    assert "password" not in created.text.lower() and "hash" not in created.text.lower()
    assert login(client, "first@example.org").status_code == 200
    assert (
        client.post(
            f"{BASE}/auth/bootstrap",
            json={**data, "email": "second@example.org"},
            headers={"X-Admin-Key": TEST_KEY},
        ).status_code
        == 409
    )


def test_login_returns_random_token_but_persists_only_hash(client, test_engine):
    wrong = login(client, password="wrong password")
    assert wrong.status_code == 401
    result = login(client)
    assert result.status_code == 200, result.text
    token = result.json()["access_token"]
    assert result.json()["token_type"] == "bearer"
    assert len(token) >= 32
    assert login(client).json()["access_token"] != token
    with Session(test_engine) as db:
        assert db.scalar(select(StaffSession).where(StaffSession.token_hash == digest_token(token)))
        assert db.scalar(select(StaffSession).where(StaffSession.token_hash == token)) is None
        staff = db.scalar(select(StaffUser).where(StaffUser.email == "admin@example.org"))
        assert staff.password_hash != PASS and check_password(staff.password_hash, PASS)
    assert (
        client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {token}"}).json()["role"]
        == "PLATFORM_ADMIN"
    )
    assert client.get(f"{BASE}/auth/me").status_code == 401
    assert (
        client.get(f"{BASE}/auth/me", headers={"Authorization": "Bearer invalid"}).status_code
        == 401
    )


def test_token_logout_and_expiry(client, test_engine):
    answer = login(client).json()
    h = {"Authorization": f"Bearer {answer['access_token']}"}
    assert client.post(f"{BASE}/auth/logout", headers=h).status_code == 204
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401
    another = login(client).json()["access_token"]
    h = {"Authorization": f"Bearer {another}"}
    with Session(test_engine) as db:
        record = db.scalar(
            select(StaffSession).where(StaffSession.token_hash == digest_token(another))
        )
        record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401


def test_change_password_revokes_every_active_session(client):
    old = login(client).json()["access_token"]
    newer = login(client).json()["access_token"]
    h = {"Authorization": f"Bearer {old}"}
    bad = client.post(
        f"{BASE}/auth/change-password",
        json={"current_password": "bad", "new_password": "NewStrongPassword!2026"},
        headers=h,
    )
    assert bad.status_code == 401
    result = client.post(
        f"{BASE}/auth/change-password",
        json={"current_password": PASS, "new_password": "NewStrongPassword!2026"},
        headers=h,
    )
    assert result.status_code == 204, result.text
    assert client.get(f"{BASE}/auth/me", headers=h).status_code == 401
    assert (
        client.get(f"{BASE}/auth/me", headers={"Authorization": f"Bearer {newer}"}).status_code
        == 401
    )
    assert login(client).status_code == 401
    assert login(client, password="NewStrongPassword!2026").status_code == 200


def test_wrong_passwords_trigger_account_lockout_then_recover(client, test_engine):
    for _ in range(5):
        assert login(client, password="bad").status_code == 401
    assert login(client).status_code == 401
    with Session(test_engine) as db:
        user = db.scalar(select(StaffUser).where(StaffUser.email == "admin@example.org"))
        assert user.locked_until is not None
        user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=1)
        db.commit()
    assert login(client).status_code == 200


def test_cannot_self_deactivate_and_inactive_tokens_revoked(client):
    assert (
        client.post(f"{BASE}/staff/{uuid.uuid4()}/deactivate", headers=admin_headers()).status_code
        == 404
    )
    me = client.get(f"{BASE}/auth/me", headers=admin_headers()).json()
    assert (
        client.post(f"{BASE}/staff/{me['id']}/deactivate", headers=admin_headers()).status_code
        == 409
    )
    created = new_staff(client, role="INTERVIEW_MANAGER", email="interviewer@example.org")
    assert created.status_code == 201, created.text
    account = created.json()
    session_header = headers_for(client, "interviewer@example.org")
    assert client.get(f"{BASE}/auth/me", headers=session_header).status_code == 200
    result = client.post(f"{BASE}/staff/{account['id']}/deactivate", headers=admin_headers())
    assert result.status_code == 200 and result.json()["is_active"] is False
    assert client.get(f"{BASE}/auth/me", headers=session_header).status_code == 401
    assert login(client, "interviewer@example.org").status_code == 401


def test_staff_roles_and_no_public_signup(client, institution):
    assert client.post(f"{BASE}/staff", json={"email": "x@example.org"}).status_code == 401
    assert client.post(f"{BASE}/auth/signup", json={}).status_code == 404
    assert new_staff(client, role="ACADEMIC_IIT", email="noinst@example.org").status_code == 422
    assert (
        new_staff(
            client,
            role="ACADEMIC_ISB",
            email="wronginst@example.org",
            institution_id=institution["id"],
        ).status_code
        == 422
    )
    valid = new_staff(
        client, role="ACADEMIC_IIT", email="iit@example.org", institution_id=institution["id"]
    )
    assert valid.status_code == 201, valid.text
    acad = headers_for(client, "iit@example.org")
    assert client.get(f"{BASE}/staff", headers=acad).status_code == 403
    assert (
        client.post(
            f"{BASE}/institutions", headers=acad, json={"code": "ABC", "name": "Other"}
        ).status_code
        == 403
    )
    assert client.get(f"{BASE}/admin/programs", headers=acad).status_code == 200
    direction = new_staff(client, role="DIRECTION", email="direction@example.org")
    assert direction.status_code == 201
    h = headers_for(client, "direction@example.org")
    assert client.get(f"{BASE}/admin/programs", headers=h).status_code == 200
    assert (
        client.post(
            f"{BASE}/admin/programs",
            json={
                "institution_id": institution["id"],
                "code": "NO",
                "title": "Nope",
                "level": "OTHER",
            },
            headers=h,
        ).status_code
        == 403
    )
    interview = new_staff(client, role="INTERVIEW_MANAGER", email="interview2@example.org")
    assert interview.status_code == 201
    h = headers_for(client, "interview2@example.org")
    assert client.get(f"{BASE}/admin/programs", headers=h).status_code == 403


def test_academic_staff_restricted_to_their_institution(client, institution):
    second = client.post(
        f"{BASE}/institutions",
        json={"code": "ISB", "name": "Institut de Business"},
        headers=admin_headers(),
    )
    assert second.status_code == 201
    isb_id = second.json()["id"]
    assert (
        new_staff(
            client,
            role="ACADEMIC_IIT",
            email="scope-iit@example.org",
            institution_id=institution["id"],
        ).status_code
        == 201
    )
    assert (
        new_staff(
            client, role="ACADEMIC_ISB", email="scope-isb@example.org", institution_id=isb_id
        ).status_code
        == 201
    )
    iit_headers = headers_for(client, "scope-iit@example.org")
    isb_headers = headers_for(client, "scope-isb@example.org")
    base_data = {"code": "PRG001", "title": "Test programme", "level": "OTHER"}
    iit_program = client.post(
        f"{BASE}/admin/programs",
        json={**base_data, "institution_id": institution["id"]},
        headers=iit_headers,
    )
    assert iit_program.status_code == 201, iit_program.text
    isb_program = client.post(
        f"{BASE}/admin/programs", json={**base_data, "institution_id": isb_id}, headers=isb_headers
    )
    assert isb_program.status_code == 201, isb_program.text
    assert client.get(f"{BASE}/admin/programs", headers=iit_headers).json()["total"] == 1
    assert client.get(f"{BASE}/admin/programs", headers=isb_headers).json()["total"] == 1
    assert client.get(f"{BASE}/admin/programs", headers=admin_headers()).json()["total"] == 2
    for method, endpoint, json_body in [
        ("get", f"{BASE}/admin/programs/{isb_program.json()['id']}", None),
        ("patch", f"{BASE}/admin/programs/{isb_program.json()['id']}", {"title": "No access"}),
        ("delete", f"{BASE}/admin/programs/{isb_program.json()['id']}", None),
    ]:
        response = getattr(client, method)(
            endpoint, headers=iit_headers, **({"json": json_body} if json_body else {})
        )
        assert response.status_code == 404, (method, response.text)
    denied = client.post(
        f"{BASE}/admin/programs", json={**base_data, "institution_id": isb_id}, headers=iit_headers
    )
    assert denied.status_code == 404
    assert (
        client.get(
            f"{BASE}/admin/programs/{isb_program.json()['id']}", headers=isb_headers
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"{BASE}/admin/programs/{isb_program.json()['id']}", headers=admin_headers()
        ).status_code
        == 200
    )


def test_public_visitor_auth_is_separate_from_staff(client):
    created = client.post(f"{BASE}/visitor/sessions").json()
    visitor_auth = {
        "X-Visitor-Token": created["access_token"]
        if "access_token" in created
        else created["token"]
    }
    assert client.get(f"{BASE}/staff", headers=visitor_auth).status_code == 401
    assert client.get(f"{BASE}/programs").status_code == 200
    assert client.get(f"{BASE}/auth/me", headers=admin_headers()).status_code == 200


def test_swagger_distinguishes_bootstrap_staff_and_visitor(client):
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert {"StaffBearer", "BootstrapKey", "VisitorSessionToken"} <= set(schemes)
    assert {"StaffBearer": []} in schema["paths"]["/api/v1/admin/programs"]["post"]["security"]
    assert {"BootstrapKey": []} in schema["paths"]["/api/v1/auth/bootstrap"]["post"]["security"]


def test_admin_can_update_role_but_revokes_existing_sessions(client, institution):
    created = new_staff(client, role="DIRECTION", email="promote@example.org")
    assert created.status_code == 201
    account_id = created.json()["id"]
    old_session = headers_for(client, "promote@example.org")
    change = client.patch(
        f"{BASE}/staff/{account_id}",
        json={"role": "ACADEMIC_IIT", "institution_id": institution["id"]},
        headers=admin_headers(),
    )
    assert change.status_code == 200, change.text
    assert change.json()["role"] == "ACADEMIC_IIT"
    assert client.get(f"{BASE}/auth/me", headers=old_session).status_code == 401
    new_session = headers_for(client, "promote@example.org")
    assert client.get(f"{BASE}/admin/programs", headers=new_session).status_code == 200
    # Changing academic scope must not be possible without matching the role.
    assert (
        client.patch(
            f"{BASE}/staff/{account_id}", json={"institution_id": None}, headers=admin_headers()
        ).status_code
        == 422
    )
    admin_id = client.get(f"{BASE}/auth/me", headers=admin_headers()).json()["id"]
    assert (
        client.patch(
            f"{BASE}/staff/{admin_id}", json={"role": "DIRECTION"}, headers=admin_headers()
        ).status_code
        == 409
    )


def test_non_admin_cannot_grant_new_roles(client, institution):
    staff = new_staff(
        client, role="ACADEMIC_IIT", email="nonadmin@example.org", institution_id=institution["id"]
    )
    assert staff.status_code == 201
    h = headers_for(client, "nonadmin@example.org")
    response = client.patch(
        f"{BASE}/staff/{staff.json()['id']}",
        json={"role": "PLATFORM_ADMIN", "institution_id": None},
        headers=h,
    )
    assert response.status_code == 403
