from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login

pytestmark = pytest.mark.integration


def test_publication_schedule_conflicts_and_live_counts(client: TestClient) -> None:
    assert client.get("/api/v1/documentation").status_code == 404
    assert client.get("/api/v1/documentation/admin").status_code == 401
    login(client, "management")
    assert client.get("/api/v1/documentation/admin").status_code == 403
    login(client, "admin")
    initial = client.get("/api/v1/documentation/admin").json()
    assert len(initial["members"]) == 5
    initial["enabled"] = True
    saved = client.put("/api/v1/documentation/admin", json=initial)
    assert saved.status_code == 200, saved.text
    public = client.get("/api/v1/documentation")
    assert public.status_code == 200
    assert public.headers["cache-control"].startswith("no-store")
    data = public.json()
    assert data["live"]["active_users"] > 0
    assert any(r["path"] == "/api/v1/documentation" for r in data["apis"])
    login(client, "admin")
    assert client.get("/api/v1/documentation").json()["live"]["audit_events"] > data["live"]["audit_events"]
    assert "password_hash" not in public.text
    assert client.put("/api/v1/documentation/admin", json=initial).status_code == 409
    body = saved.json()
    body["show_team"] = False
    hidden_id = body["sections"][0]["id"]
    body["sections"][0]["visible"] = False
    saved = client.put("/api/v1/documentation/admin", json=body)
    public_content = client.get("/api/v1/documentation").json()["content"]
    assert public_content["members"] == []
    assert all(section["id"] != hidden_id for section in public_content["sections"])
    body = saved.json()
    body["starts_at"] = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    saved = client.put("/api/v1/documentation/admin", json=body)
    assert saved.status_code == 200
    assert client.get("/api/v1/documentation").status_code == 404
    assert client.get("/api/v1/documentation/preview").status_code == 200
    body = saved.json()
    body["ends_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert client.put("/api/v1/documentation/admin", json=body).status_code == 422
    body["starts_at"] = None
    saved = client.put("/api/v1/documentation/admin", json=body)
    assert saved.status_code == 200
    assert client.get("/api/v1/documentation").status_code == 404


def test_invalid_images_and_links(client: TestClient) -> None:
    login(client, "admin")
    body = client.get("/api/v1/documentation/admin").json()
    body["members"][0]["image_data"] = "data:image/svg+xml;base64,PHN2Zz4="
    assert client.put("/api/v1/documentation/admin", json=body).status_code == 422
    body["members"][0]["image_data"] = None
    body["app_url"] = "javascript:alert(1)"
    assert client.put("/api/v1/documentation/admin", json=body).status_code == 422
