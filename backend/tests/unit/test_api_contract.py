"""API contract checks that need no database: OpenAPI drift, auth on every route, event schema."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from threadeye.api.app import create_app
from threadeye.api.introspect import iter_api_routes
from threadeye.api.schemas.events import EventEnvelope, EventType

OPENAPI_FILE = Path(__file__).resolve().parents[3] / "docs" / "api" / "openapi.json"
PUBLIC = {("POST", "/api/v1/auth/login"), ("GET", "/health")}


def test_openapi_snapshot_is_current() -> None:
    """docs/api/openapi.json is the agreed contract; regenerate with `make openapi`."""
    generated = create_app().openapi()
    committed = json.loads(OPENAPI_FILE.read_text(encoding="utf-8"))
    assert generated == committed, "OpenAPI drift: run `make openapi` and commit the result"


def test_every_route_except_login_and_health_requires_a_session() -> None:
    routes = list(iter_api_routes(create_app()))
    assert len(routes) >= 45, "route discovery broke (FastAPI internals changed?)"
    unguarded = [
        f"{method} {r.path}"
        for r in routes
        for method in r.methods
        if (method, r.path) not in PUBLIC and not r.needs_session
    ]
    assert unguarded == []


def test_event_envelope() -> None:
    e = EventEnvelope(
        inspection_id=uuid4(),
        seq=1,
        type=EventType.DEFECT_UPSERTED,
        at=datetime.now(UTC),
        actor={"kind": "engine"},
        simulated=True,
        provider="simulated@0.1.0",
        payload={"defect": {}},
    )
    assert EventEnvelope.model_validate_json(e.model_dump_json()) == e
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate({**e.model_dump(), "seq": 0})
    with pytest.raises(ValidationError):
        EventEnvelope.model_validate({**e.model_dump(), "type": "made.up"})
