import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import TEST_PASSWORD, login
from threadeye.db.models import AuditLog
from threadeye.db.session import get_sessionmaker
from threadeye.settings import get_settings

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("provider, simulated", [("simulated", True), ("local_model", False)])
def test_health_runs_a_db_query(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, provider: str, simulated: bool
) -> None:
    monkeypatch.setattr(get_settings(), "detector_provider", provider)
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["db"] == "ok"
    assert body["profile"] == "edge"
    assert body["simulated_mode"] is simulated


def test_login_sets_httponly_cookie_and_me_works(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"username": "Inspector", "password": TEST_PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "te_session=" in cookie and "httponly" in cookie and "samesite=lax" in cookie
    me = client.get("/api/v1/auth/me").json()
    assert me["username"] == "inspector"
    assert me["role"] == "inspector"
    assert me["locale"] == "bn"
    assert "defects.confirm" in me["permissions"]
    assert "users.manage" not in me["permissions"]


def test_wrong_password_is_rejected_and_audited(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"username": "inspector", "password": "nope-nope-nope"})
    assert r.status_code == 401
    r = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "nope-nope-nope"})
    assert r.status_code == 401
    with get_sessionmaker()() as db:
        actions = db.scalars(select(AuditLog.entity_id).where(AuditLog.action == "auth.login_failed")).all()
    assert sorted(actions) == ["ghost", "inspector"]


def test_lockout_after_repeated_failures(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "login_max_failures", 3)
    for _ in range(3):
        assert client.post("/api/v1/auth/login", json={"username": "store", "password": "x" * 12}).status_code == 401
    r = client.post("/api/v1/auth/login", json={"username": "store", "password": TEST_PASSWORD})
    assert r.status_code == 429


def test_logout_revokes_the_session(client: TestClient) -> None:
    login(client, "supervisor")
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401


def test_patch_me_changes_locale_and_is_audited(client: TestClient) -> None:
    login(client, "inspector")
    r = client.patch("/api/v1/auth/me", json={"locale": "en", "digit_style": "bengali"})
    assert r.status_code == 200
    assert r.json()["locale"] == "en"
    with get_sessionmaker()() as db:
        row = db.scalars(select(AuditLog).where(AuditLog.action == "user.update_self")).one()
    assert row.before == {"locale": "bn", "digit_style": "latin"}
    assert row.after == {"locale": "en", "digit_style": "bengali"}


def test_cross_origin_state_change_is_rejected(client: TestClient) -> None:
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "inspector", "password": TEST_PASSWORD},
        headers={"Origin": "http://evil.example"},
    )
    assert r.status_code == 403
    r = client.post(
        "/api/v1/auth/login",
        json={"username": "inspector", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:8080"},
    )
    assert r.status_code == 200
