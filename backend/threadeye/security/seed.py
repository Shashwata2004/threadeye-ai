"""Demo accounts (one per role) for the local edge box and the cloud demo.

The password comes from THREADEYE_DEMO_PASSWORD, never from code. Accounts are created only if
missing, so running this again is safe.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from threadeye.db import audit
from threadeye.db.models import User
from threadeye.security.passwords import hash_password
from threadeye.security.rbac import DEFAULT_LOCALE, Role

DEMO_USERS: tuple[tuple[str, str, Role], ...] = (
    ("inspector", "Demo Inspector", Role.INSPECTOR),
    ("supervisor", "Demo QC Supervisor", Role.QC_SUPERVISOR),
    ("store", "Demo Store In-charge", Role.STORE_INCHARGE),
    ("cutting", "Demo Cutting Master", Role.CUTTING_MASTER),
    ("merchandiser", "Demo Merchandiser", Role.MERCHANDISER),
    ("management", "Demo Management", Role.MANAGEMENT),
    ("admin", "Demo Admin", Role.ADMIN),
)


def seed_demo_users(db: Session, password: str) -> list[str]:
    created: list[str] = []
    pw_hash = hash_password(password)
    for username, display, role in DEMO_USERS:
        if db.scalar(select(User.id).where(User.username == username)):
            continue
        db.add(
            User(
                username=username,
                display_name=display,
                password_hash=pw_hash,
                role=role.value,
                locale=DEFAULT_LOCALE[role],
            )
        )
        created.append(username)
    if created:
        db.flush()
        audit.record(
            db,
            action="system.seed_demo_users",
            entity_type="user",
            after={"created": created, "sample_data": True},
        )
    db.commit()
    return created
