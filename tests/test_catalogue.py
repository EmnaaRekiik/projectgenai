from datetime import datetime, timedelta, timezone


def test_live_and_ready(client):
    assert client.get("/api/v1/health/live").json() == {"status": "alive"}
    assert client.get("/api/v1/health/ready").json()["status"] == "ready"


def test_openapi_exposes_staff_bearer_security(client):
    schema = client.get("/openapi.json").json()
    assert "StaffBearer" in schema["components"]["securitySchemes"]
    protected = schema["paths"]["/api/v1/admin/programs"]["post"]
    assert {"StaffBearer": []} in protected["security"]


def test_staff_bearer_required_for_writes(client, institution):
    data = {"institution_id": institution["id"], "code": "X1", "title": "Demo", "level": "OTHER"}
    assert client.post("/api/v1/admin/programs", json=data).status_code == 401
    assert (
        client.post(
            "/api/v1/admin/programs", json=data, headers={"Authorization": "Bearer wrong"}
        ).status_code
        == 401
    )
    assert client.get("/api/v1/admin/programs").status_code == 401
    assert client.get("/api/v1/programs").status_code == 200


def test_institution_list_and_uniqueness(client, headers, institution):
    items = client.get("/api/v1/institutions").json()
    assert len(items) == 1 and items[0]["code"] == "IIT"
    assert client.get(f"/api/v1/institutions/{institution['id']}").status_code == 200
    duplicate = client.post(
        "/api/v1/institutions", json={"code": "IIT", "name": "Another"}, headers=headers
    )
    assert duplicate.status_code == 409


def test_create_program_always_draft(client, draft):
    assert draft["status"] == "DRAFT"
    assert draft["code"] == "DEMO-LIC-1"
    assert client.get("/api/v1/programs").json()["total"] == 0
    assert client.get(f"/api/v1/programs/{draft['id']}").status_code == 404


def test_program_admin_listing_and_details(client, headers, draft):
    result = client.get("/api/v1/admin/programs", headers=headers).json()
    assert result["total"] == 1
    assert result["items"][0]["id"] == draft["id"]
    assert (
        client.get(f"/api/v1/admin/programs/{draft['id']}", headers=headers).json()["status"]
        == "DRAFT"
    )


def test_dont_publish_without_source(client, headers, draft):
    response = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={"status": "PUBLISHED"},
        headers=headers,
    )
    assert response.status_code == 422
    assert client.get("/api/v1/programs").json()["total"] == 0


def test_publish_with_source_then_public_search(client, headers, draft, institution):
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    result = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={
            "official_source_url": "https://example.edu/verified-document",
            "verified_at": yesterday,
            "status": "PUBLISHED",
        },
        headers=headers,
    )
    assert result.status_code == 200, result.text
    response = client.get(
        "/api/v1/programs", params={"level": "LICENCE", "institution_id": institution["id"]}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["items"][0]["title"] == draft["title"]
    assert client.get("/api/v1/programs", params={"q": "fictive"}).json()["total"] == 1
    assert client.get("/api/v1/programs", params={"q": "nonsense"}).json()["total"] == 0
    assert client.get(f"/api/v1/programs/{draft['id']}").status_code == 200


def test_future_source_verification_denied(client, headers, draft):
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    result = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={
            "official_source_url": "https://example.edu/doc",
            "verified_at": tomorrow,
            "status": "PUBLISHED",
        },
        headers=headers,
    )
    assert result.status_code == 422


def test_duplicate_program_code_per_institution(client, headers, institution, draft):
    duplicate = client.post(
        "/api/v1/admin/programs",
        json={
            "institution_id": institution["id"],
            "code": "DEMO-LIC-1",
            "title": "Different title",
            "level": "OTHER",
        },
        headers=headers,
    )
    assert duplicate.status_code == 409


def test_program_validation(client, headers, institution):
    base = {
        "institution_id": institution["id"],
        "code": "INVALID1",
        "title": "Example title",
        "level": "OTHER",
    }
    for change in ({"duration_years": 11}, {"level": "NOT_A_LEVEL"}, {"code": "lowercase"}):
        assert (
            client.post("/api/v1/admin/programs", json=base | change, headers=headers).status_code
            == 422
        )
    assert (
        client.post(
            "/api/v1/admin/programs",
            json=base | {"institution_id": "00000000-0000-0000-0000-000000000000"},
            headers=headers,
        ).status_code
        == 404
    )


def test_archive_keeps_record_but_hides_publicly(client, headers, draft):
    published = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={
            "official_source_url": "https://example.edu/verified",
            "verified_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "status": "PUBLISHED",
        },
        headers=headers,
    )
    assert published.status_code == 200, published.text
    assert client.get("/api/v1/programs").json()["total"] == 1
    response = client.delete(f"/api/v1/admin/programs/{draft['id']}", headers=headers)
    assert response.status_code == 204
    assert client.get("/api/v1/programs").json()["total"] == 0
    assert (
        client.get(f"/api/v1/admin/programs/{draft['id']}", headers=headers).json()["status"]
        == "ARCHIVED"
    )


def test_draft_patch_and_pagination(client, headers, institution, draft):
    updated = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={"title": "New title", "duration_years": 2},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "New title"
    assert updated.json()["duration_years"] == 2
    second = client.post(
        "/api/v1/admin/programs",
        json={
            "institution_id": institution["id"],
            "code": "SECOND",
            "title": "Another draft",
            "level": "OTHER",
        },
        headers=headers,
    )
    assert second.status_code == 201
    result = client.get("/api/v1/admin/programs?limit=1&offset=1", headers=headers).json()
    assert result["total"] == 2 and len(result["items"]) == 1
    assert client.get("/api/v1/admin/programs?limit=101", headers=headers).status_code == 422


def test_cannot_null_required_fields(client, headers, draft):
    for field in ("title", "status", "level"):
        res = client.patch(
            f"/api/v1/admin/programs/{draft['id']}",
            json={field: None},
            headers=headers,
        )
        assert res.status_code == 422


def test_institution_create_requires_key(client):
    res = client.post("/api/v1/institutions", json={"code": "ISB", "name": "ISB"})
    assert res.status_code == 401


def test_edit_published_program_without_reverifying_source(client, headers, draft):
    res = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={
            "official_source_url": "https://example.edu/verified",
            "verified_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "status": "PUBLISHED",
        },
        headers=headers,
    )
    assert res.status_code == 200
    res = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={"title": "Revised publication"},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    assert client.get(f"/api/v1/programs/{draft['id']}").json()["title"] == "Revised publication"


def test_http_source_cannot_be_published(client, headers, draft):
    res = client.patch(
        f"/api/v1/admin/programs/{draft['id']}",
        json={
            "official_source_url": "http://example.edu/doc",
            "verified_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "status": "PUBLISHED",
        },
        headers=headers,
    )
    assert res.status_code == 422


def test_reject_whitespace_titles_and_unknown_fields(client, headers, institution):
    payload = {
        "institution_id": institution["id"],
        "code": "WHITESPACE",
        "title": "   ",
        "level": "OTHER",
    }
    assert client.post("/api/v1/admin/programs", json=payload, headers=headers).status_code == 422
    payload["title"] = "A valid title"
    payload["surprise"] = "not in API contract"
    assert client.post("/api/v1/admin/programs", json=payload, headers=headers).status_code == 422
