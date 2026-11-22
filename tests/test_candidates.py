"""Candidate identity, RBAC boundary, secret revocation and email proof."""

from app.core.config import Settings, get_settings
from app.main import app

REGISTER = "/api/v1/candidates/register"
LOGIN = "/api/v1/candidates/login"
PASSWORD = "Candidate_123456789!"


def make_account(client, email="candidate@example.org"):
    response = client.post(
        REGISTER, json={"email": email, "display_name": "Etudiant candidat", "password": PASSWORD}
    )
    assert response.status_code == 201, response.text
    return response.json()


def login(client, email="candidate@example.org", password=PASSWORD):
    return client.post(LOGIN, json={"email": email, "password": password})


def test_candidate_lifecycle_and_role_isolation(client, headers):
    user = make_account(client)
    assert user["email_verified_at"] is None
    assert "password_hash" not in user
    assert client.get("/api/v1/candidates/me").status_code == 401
    auth = login(client)
    assert auth.status_code == 200, auth.text
    token = auth.json()["access_token"]
    bearer = {"Authorization": "Bearer " + token}
    assert client.get("/api/v1/candidates/me", headers=bearer).json()["id"] == user["id"]
    # Candidate cannot use staff-only tokens to modify the academic catalogue.
    assert (
        client.post(
            "/api/v1/institutions", headers=bearer, json={"code": "FAKE", "name": "Fake campus"}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/auth/me", headers=bearer).status_code == 401
    assert client.get("/api/v1/candidates/me", headers=headers).status_code == 401
    updated = client.patch(
        "/api/v1/candidates/me",
        headers=bearer,
        json={
            "education_level": "Bac sciences",
            "interests": ["Maths", "Informatique"],
            "career_goal": "Software engineer",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["interests"] == ["Maths", "Informatique"]
    assert client.post("/api/v1/candidates/logout", headers=bearer).status_code == 204
    assert client.get("/api/v1/candidates/me", headers=bearer).status_code == 401
    assert login(client).status_code == 200


def test_duplicate_and_invalid_registration(client):
    make_account(client)
    assert (
        client.post(
            REGISTER,
            json={
                "email": "candidate@example.org",
                "display_name": "Another",
                "password": PASSWORD,
            },
        ).status_code
        == 409
    )
    assert (
        client.post(
            REGISTER, json={"email": "bad-email", "display_name": "A", "password": "short"}
        ).status_code
        == 422
    )
    assert login(client, password="wrongpw").status_code == 401


def test_candidate_password_change_revokes_all_tokens(client):
    make_account(client)
    one = login(client).json()["access_token"]
    two = login(client).json()["access_token"]
    changed = client.post(
        "/api/v1/candidates/change-password",
        headers={"Authorization": f"Bearer {one}"},
        json={"current_password": PASSWORD, "new_password": "New_stronger_password_123!"},
    )
    assert changed.status_code == 204, changed.text
    assert (
        client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {one}"}).status_code
        == 401
    )
    assert (
        client.get("/api/v1/candidates/me", headers={"Authorization": f"Bearer {two}"}).status_code
        == 401
    )
    assert login(client, password=PASSWORD).status_code == 401
    assert login(client, password="New_stronger_password_123!").status_code == 200


def test_candidate_email_verification_with_smtp_mock(client, monkeypatch):
    sent = []
    import app.api.routers.candidates as target

    monkeypatch.setattr(
        target,
        "send_verification_email",
        lambda email, token, settings: sent.append((email, token)) or True,
    )
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql+psycopg://test:test@localhost/not_used",
        admin_api_key="test-key-not-for-production-12345678901234567890",
        smtp_host="smtp.test.local",
        smtp_from="noreply@example.org",
    )
    make_account(client)
    assert len(sent) == 1
    token = sent[0][1]
    assert len(token) > 32
    assert (
        client.post("/api/v1/candidates/verify-email", json={"token": "x" * 45}).status_code == 400
    )
    assert client.post("/api/v1/candidates/verify-email", json={"token": token}).status_code == 204
    assert client.post("/api/v1/candidates/verify-email", json={"token": token}).status_code == 400
    auth = login(client)
    assert auth.json()["user"]["email_verified_at"] is not None


def test_resend_without_smtp_explicitly_unavailable(client):
    make_account(client)
    token = login(client).json()["access_token"]
    assert (
        client.post(
            "/api/v1/candidates/resend-verification", headers={"Authorization": "Bearer " + token}
        ).status_code
        == 503
    )


def test_lockout_on_five_failed_passwords(client):
    make_account(client)
    for i in range(5):
        assert login(client, password="notcorrect").status_code == 401
    assert login(client).status_code == 401


def test_registration_rate_limited_by_server_side_bucket(client):
    app.dependency_overrides[get_settings] = lambda: Settings(
        database_url="postgresql+psycopg://test:test@localhost/not_used",
        admin_api_key="test-key-not-for-production-12345678901234567890",
        candidate_registrations_per_hour=2,
    )
    make_account(client, "first@example.org")
    make_account(client, "second@example.org")
    result = client.post(
        REGISTER,
        json={"email": "third@example.org", "display_name": "A student", "password": PASSWORD},
    )
    assert result.status_code == 429, result.text
    assert "Retry-After" in result.headers


def test_candidate_can_delete_own_account(client):
    make_account(client)
    token = login(client).json()["access_token"]
    bearer = {"Authorization": "Bearer " + token}
    assert client.delete("/api/v1/candidates/me", headers=bearer).status_code == 204
    assert client.get("/api/v1/candidates/me", headers=bearer).status_code == 401
    assert login(client).status_code == 401
