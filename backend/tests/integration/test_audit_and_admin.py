import psycopg
import pytest
import sqlalchemy.exc
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import TEST_PASSWORD, login
from threadeye.db.session import get_engine
from threadeye.jobs.worker import Worker

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE threadeye.audit_log SET action = 'tampered'",
        "DELETE FROM threadeye.audit_log",
        "TRUNCATE threadeye.audit_log",
    ],
)
def test_audit_log_is_append_only(client: TestClient, sql: str) -> None:
    login(client, "admin")  # guarantees at least one audit row
    with pytest.raises(sqlalchemy.exc.DBAPIError) as exc, get_engine().begin() as conn:
        conn.execute(text(sql))
    assert isinstance(exc.value.orig, psycopg.errors.InsufficientPrivilege)
    assert "append-only" in str(exc.value.orig)


def test_audit_chain_verifies_and_detects_tampering(client: TestClient) -> None:
    login(client, "inspector")
    login(client, "admin")
    r = client.get("/api/v1/audit/verify")
    assert r.status_code == 200
    assert r.json()["ok"] is True and r.json()["checked"] >= 3

    with get_engine().begin() as conn:  # a DB superuser/owner bypassing the trigger
        conn.execute(text("ALTER TABLE threadeye.audit_log DISABLE TRIGGER USER"))
        conn.execute(text("UPDATE threadeye.audit_log SET actor_role = 'admin' WHERE id = 2"))
        conn.execute(text("ALTER TABLE threadeye.audit_log ENABLE TRIGGER USER"))
    body = client.get("/api/v1/audit/verify").json()
    assert body["ok"] is False
    assert body["first_bad_id"] == 2


def test_audit_listing_is_restricted(client: TestClient) -> None:
    login(client, "management")
    assert client.get("/api/v1/audit?limit=5").status_code == 200
    login(client, "inspector")
    assert client.get("/api/v1/audit").status_code == 403


def test_admin_user_lifecycle(client: TestClient) -> None:
    login(client, "admin")
    r = client.post(
        "/api/v1/users",
        json={"username": "rina", "display_name": "Rina", "role": "inspector", "password": "a-long-password"},
    )
    assert r.status_code == 201, r.text
    uid = r.json()["id"]
    assert r.json()["locale"] == "bn"
    assert (
        client.post(
            "/api/v1/users",
            json={"username": "rina", "display_name": "Dup", "role": "inspector", "password": "a-long-password"},
        ).status_code
        == 409
    )

    other = TestClient(client.app)
    login(other, "rina", "a-long-password")
    assert other.get("/api/v1/auth/me").status_code == 200
    assert client.patch(f"/api/v1/users/{uid}", json={"active": False}).status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401  # sessions revoked

    me = client.get("/api/v1/auth/me").json()
    assert client.patch(f"/api/v1/users/{me['id']}", json={"active": False}).status_code == 400


def test_system_status_reports_worker_and_simulated_provider(client: TestClient) -> None:
    login(client, "inspector", TEST_PASSWORD)
    s = client.get("/api/v1/system/status").json()
    assert s["db"] == "ok"
    assert s["worker"]["alive"] is False
    assert s["simulated_mode"] is True
    assert s["active_provider"]["provider_id"] == "simulated"

    Worker().heartbeat()
    assert client.get("/api/v1/system/status").json()["worker"]["alive"] is True

    providers = {p["provider_id"]: p for p in client.get("/api/v1/providers").json()}
    assert providers["simulated"]["active"] is True and providers["simulated"]["is_simulated"] is True
    # The trained model can be chosen (THREADEYE_DETECTOR_PROVIDER=local_model) but is not the active one here.
    assert providers["local_model"]["availability"] == "available" and providers["local_model"]["active"] is False
    assert providers["local_model"]["is_simulated"] is False
    assert providers["api"]["availability"] == "stub"


def test_migrations_match_models(migrated_db: str) -> None:
    from alembic import command

    from threadeye.db.migrate import alembic_config

    command.check(alembic_config(migrated_db))  # raises if autogenerate would emit changes
