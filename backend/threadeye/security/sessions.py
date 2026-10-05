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
    if not token:
        return None
    row = db.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == _hash(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
            User.active.is_(True),
        )
    ).first()
    return row[0] if row else None


def session_id(db: Session, token: str | None) -> uuid.UUID | None:
    """Id of the caller's live session (the live screen's driver lease is held per session)."""
    if not token:
        return None
    return db.scalar(
        select(AuthSession.id).where(
            AuthSession.token_hash == _hash(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(UTC),
        )
    )


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
