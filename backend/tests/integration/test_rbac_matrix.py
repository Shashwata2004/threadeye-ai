"""Every guarded endpoint × every role: 403 exactly when the role lacks the permission (PLAN.md §11).

Routes are discovered from the app, so new endpoints are covered automatically. Permission checks
run before body/path validation, so "allowed" shows up as anything other than 401/403 (e.g. 501 for
contract-v0 stubs, or 422 for the empty test body).
"""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import login
from threadeye.api.app import create_app
from threadeye.api.introspect import iter_api_routes
from threadeye.security.rbac import Perm, Role, has_perm
from threadeye.security.seed import DEMO_USERS

pytestmark = pytest.mark.integration

USER_FOR_ROLE = {role: username for username, _, role in DEMO_USERS}


def guarded_routes() -> list[tuple[str, str, Perm]]:
    return [
        (method, r.path, r.perm)
        for r in iter_api_routes(create_app())
        if r.perm is not None
        for method in sorted(r.methods)
    ]


ROUTES = guarded_routes()


def concrete(path: str) -> str:
    out = path
    for name in ("lot_id", "roll_id", "inspection_id", "defect_id", "user_id"):
        out = out.replace("{" + name + "}", str(uuid.uuid4()))
    return out.replace("{roll_code}", "R-0001").replace("{dataset_id}", "no_such_roll")


def test_discovered_a_meaningful_number_of_guarded_routes() -> None:
    assert len(ROUTES) >= 40


@pytest.mark.parametrize("role", list(Role))
def test_role_matrix(client: TestClient, role: Role) -> None:
    login(client, USER_FOR_ROLE[role])
    wrong = []
    for method, path, perm in ROUTES:
        r = client.request(method, concrete(path), json={} if method in {"POST", "PATCH"} else None)
        forbidden = r.status_code == 403
        if forbidden == has_perm(role, perm) or r.status_code == 401:
            wrong.append(f"{method} {path} → {r.status_code} (perm {perm.value})")
    assert wrong == []


def test_anonymous_gets_401_everywhere(client: TestClient) -> None:
    for method, path, _ in ROUTES:
        r = client.request(method, concrete(path), json={} if method in {"POST", "PATCH"} else None)
        assert r.status_code == 401, f"{method} {path} → {r.status_code}"


def test_measurement_requires_a_real_inspection(client: TestClient) -> None:
    login(client, "inspector")
    r = client.post(
        f"/api/v1/inspections/{uuid.uuid4()}/measurements", json={"kind": "width", "value": 58, "unit": "in"}
    )
    assert r.status_code == 404
