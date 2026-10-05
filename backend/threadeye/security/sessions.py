"""Server-side sessions: a random token in an httpOnly cookie; only its SHA-256 is stored."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from threadeye.db.models import AuthSession, User

COOKIE_NAME = "te_session"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User, *, ttl_hours: int, ip: str | None, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=_hash(token),
            expires_at=datetime.now(UTC) + timedelta(hours=ttl_hours),
            ip=ip,
            user_agent=(user_agent or "")[:256] or None,
        )
    )
    return token


def resolve(db: Session, token: str | None) -> User | None:
    found = resolve_with_session(db, token)
    return found[0] if found else None


def resolve_with_session(db: Session, token: str | None) -> tuple[User, uuid.UUID] | None:
    """The logged-in user and the id of their session, in one query."""
    if not token:
        return None
    row = db.execute(
        select(User, AuthSession.id)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == _hash(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
            User.active.is_(True),
        )
    ).first()
    return (row[0], row[1]) if row else None


def revoke(db: Session, token: str | None) -> None:
    if token:
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == _hash(token), AuthSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )


def revoke_all_for_user(db: Session, user: User) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
