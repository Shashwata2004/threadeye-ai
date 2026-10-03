"""Append-only, hash-chained audit log.

Every user-initiated command writes one row in the same transaction as the change. Each row's hash
is ``sha256(prev_hash + canonical_json(fields))``, so editing or deleting any past row (which the
DB triggers already forbid) is also detectable by ``verify_chain``.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from threadeye.db.models import AuditLog

GENESIS_HASH = "0" * 64
_AUDIT_LOCK_KEY = 0x7468726561647965  # "threadye": serialises chain appends across connections


def canonical(fields: dict[str, Any]) -> str:
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def compute_hash(prev_hash: str, fields: dict[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical(fields)).encode("utf-8")).hexdigest()


def _fields(row: AuditLog) -> dict[str, Any]:
    return {
        "at": row.at.astimezone(UTC).isoformat(),
        "actor_user_id": str(row.actor_user_id) if row.actor_user_id else None,
        "actor_role": row.actor_role,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": row.entity_id,
        "before": row.before,
        "after": row.after,
        "ip": row.ip,
        "request_id": row.request_id,
    }


def record(
    db: Session,
    *,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    actor_role: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    request_id: str | None = None,
) -> AuditLog:
    """Append one audit row. The caller commits (same transaction as the audited change)."""
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_LOCK_KEY})
    prev = db.scalar(select(AuditLog.hash).order_by(AuditLog.id.desc()).limit(1)) or GENESIS_HASH
    row = AuditLog(
        at=datetime.now(UTC),
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        ip=ip,
        request_id=request_id,
        prev_hash=prev,
    )
    row.hash = compute_hash(prev, _fields(row))
    db.add(row)
    db.flush()
    return row


@dataclass(frozen=True)
class ChainReport:
    ok: bool
    checked: int
    first_bad_id: int | None
    reason: str | None


def verify_chain(db: Session, batch: int = 1000) -> ChainReport:
    prev = GENESIS_HASH
    checked = 0
    last_id = 0
    while True:
        rows = db.scalars(select(AuditLog).where(AuditLog.id > last_id).order_by(AuditLog.id).limit(batch)).all()
        if not rows:
            return ChainReport(ok=True, checked=checked, first_bad_id=None, reason=None)
        for row in rows:
            if row.prev_hash != prev:
                return ChainReport(False, checked, row.id, "prev_hash does not match previous row")
            if compute_hash(prev, _fields(row)) != row.hash:
                return ChainReport(False, checked, row.id, "row content does not match its hash")
            prev = row.hash
            checked += 1
            last_id = row.id
