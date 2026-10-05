"""Shared fixtures.

Unit tests need nothing. Integration tests (marked ``integration``) need a throwaway PostgreSQL:
``TEST_DATABASE_URL`` (``make test`` starts one on :55432; CI uses a service container). Without it
they are skipped locally; in CI (``CI=true``) a missing database is an error.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

# Live inspections read simulated rolls from here (the micro-fixture) and store evidence images in a
# throwaway directory. Must be set before threadeye.settings is first used.
os.environ.setdefault("THREADEYE_DATASETS_DIR", str(Path(__file__).parent / "fixtures"))
os.environ.setdefault("THREADEYE_STORAGE_DIR", tempfile.mkdtemp(prefix="threadeye-test-storage-"))

_TEST_DB = os.environ.get("TEST_DATABASE_URL")
if _TEST_DB:
    # Must be set before threadeye.settings is first used.
    os.environ["THREADEYE_DATABASE_URL"] = _TEST_DB
    os.environ.setdefault("THREADEYE_ALLOWED_ORIGINS", "http://localhost:8080")

from fastapi.testclient import TestClient  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"
MICRO_ROLL = FIXTURES / "micro_roll"
REPO_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_ROLL = REPO_ROOT / "data" / "sample_roll"
TEST_PASSWORD = "test-password-123"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _TEST_DB:
        return
    if os.environ.get("CI"):
        raise pytest.UsageError("TEST_DATABASE_URL must be set in CI")
    skip = pytest.mark.skip(reason="TEST_DATABASE_URL not set (run `make test`)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def migrated_db() -> Iterator[str]:
    from alembic import command
    from sqlalchemy import create_engine, text

    from threadeye.db.migrate import alembic_config

    assert _TEST_DB
    engine = create_engine(_TEST_DB)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS threadeye CASCADE"))
    engine.dispose()
    command.upgrade(alembic_config(_TEST_DB), "head")
    yield _TEST_DB


@pytest.fixture
def clean_db(migrated_db: str) -> Iterator[None]:
    """Empty every table. The audit log's append-only triggers are disabled only for this reset."""
    from sqlalchemy import text

    from threadeye.db.session import get_engine

    append_only = ("audit_log", "inspection_events")
    with get_engine().begin() as conn:
        tables = conn.scalars(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'threadeye' AND tablename <> 'alembic_version'")
        ).all()
        for t in append_only:
            conn.execute(text(f"ALTER TABLE threadeye.{t} DISABLE TRIGGER USER"))
        conn.execute(text("TRUNCATE " + ", ".join(f"threadeye.{t}" for t in tables) + " RESTART IDENTITY CASCADE"))
        for t in append_only:
            conn.execute(text(f"ALTER TABLE threadeye.{t} ENABLE TRIGGER USER"))
    yield


@pytest.fixture
def seeded(clean_db: None) -> None:
    from threadeye.db.session import get_sessionmaker
    from threadeye.security.seed import seed_demo_users
    from threadeye.services.receiving import seed_sample_data

    with get_sessionmaker()() as db:
        seed_demo_users(db, TEST_PASSWORD)
        seed_sample_data(db)


@pytest.fixture
def client(seeded: None) -> Iterator[TestClient]:
    from threadeye.api.app import create_app

    with TestClient(create_app()) as c:
        yield c


def login(client: TestClient, username: str, password: str = TEST_PASSWORD) -> None:
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
