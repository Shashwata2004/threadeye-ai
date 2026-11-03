"""Public mode disclosure must agree with the configured detector, even on DB failure."""

import json

import pytest

from threadeye.api.routers import health
from threadeye.settings import Settings


@pytest.mark.parametrize("provider, simulated", [("simulated", True), ("local_model", False), ("unknown", True)])
@pytest.mark.parametrize("db_ok", [True, False])
def test_health_discloses_provider_mode(
    monkeypatch: pytest.MonkeyPatch, provider: str, simulated: bool, db_ok: bool
) -> None:
    monkeypatch.setattr(health, "get_settings", lambda: Settings(detector_provider=provider))
    monkeypatch.setattr(health, "ping", lambda: db_ok)
    monkeypatch.setattr(health, "current_provider", lambda _: provider)
    response = health.health()
    assert response.status_code == (200 if db_ok else 503)
    assert json.loads(response.body)["simulated_mode"] is simulated


def test_db_exception_does_not_change_mode_or_expose_details(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(health, "get_settings", lambda: Settings(detector_provider="local_model"))

    def unavailable() -> bool:
        raise RuntimeError("private connection details")

    monkeypatch.setattr(health, "ping", unavailable)
    response = health.health()
    assert response.status_code == 503
    assert json.loads(response.body)["simulated_mode"] is False
    assert b"private connection" not in response.body
