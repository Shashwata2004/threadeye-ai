import time
import uuid

import pytest

from threadeye.core.ids import uuid7
from threadeye.db.audit import GENESIS_HASH, canonical, compute_hash
from threadeye.security.passwords import hash_password, verify_password
from threadeye.security.rbac import DEFAULT_LOCALE, ROLE_PERMS, Perm, Role, has_perm, perms_for


def test_every_role_has_permissions_and_a_default_locale() -> None:
    assert set(ROLE_PERMS) == set(Role)
    assert set(DEFAULT_LOCALE) == set(Role)
    assert ROLE_PERMS[Role.ADMIN] == frozenset(Perm)


@pytest.mark.parametrize(
    ("role", "perm", "allowed"),
    [
        (Role.INSPECTOR, Perm.DEFECTS_CONFIRM, True),
        (Role.INSPECTOR, Perm.VERDICT_DECIDE, False),
        (Role.INSPECTOR, Perm.USERS_MANAGE, False),
        (Role.INSPECTOR, Perm.DASHBOARD_READ, False),  # own-shift summary only (no surveillance)
        (Role.QC_SUPERVISOR, Perm.VERDICT_DECIDE, True),
        (Role.STORE_INCHARGE, Perm.LOTS_WRITE, True),
        (Role.STORE_INCHARGE, Perm.DEFECTS_CONFIRM, False),
        (Role.CUTTING_MASTER, Perm.CUTTING_ACKNOWLEDGE, True),
        (Role.CUTTING_MASTER, Perm.CUTTING_APPROVE, False),
        (Role.MERCHANDISER, Perm.CLAIMS_WRITE, True),
        (Role.MANAGEMENT, Perm.AUDIT_READ, True),
        (Role.MANAGEMENT, Perm.LOTS_WRITE, False),
    ],
)
def test_role_permission_matrix(role: Role, perm: Perm, allowed: bool) -> None:
    assert has_perm(role, perm) is allowed


def test_unknown_role_has_nothing() -> None:
    assert has_perm("hacker", Perm.LOTS_READ) is False
    assert perms_for("hacker") == []


def test_password_hashing_is_argon2id() -> None:
    h = hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "correct horse battery")
    assert not verify_password(h, "wrong password!!")
    assert not verify_password("not-a-hash", "whatever")
    with pytest.raises(ValueError):
        hash_password("short")


def test_uuid7_is_version_7_and_time_ordered() -> None:
    a = uuid7()
    time.sleep(0.002)
    b = uuid7()
    assert a.version == 7 and b.version == 7
    assert a.variant == uuid.RFC_4122
    assert a.int < b.int


def test_audit_hash_is_deterministic_and_content_sensitive() -> None:
    fields = {"action": "auth.login", "b": None, "a": 1}
    assert canonical(fields) == canonical({"a": 1, "action": "auth.login", "b": None})
    h1 = compute_hash(GENESIS_HASH, fields)
    assert h1 == compute_hash(GENESIS_HASH, dict(fields))
    assert h1 != compute_hash(GENESIS_HASH, {**fields, "action": "auth.logout"})
    assert h1 != compute_hash("f" * 64, fields)
