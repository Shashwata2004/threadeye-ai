"""ORM models. M0 baseline: users, sessions, audit log, settings, component heartbeats.

The inspection domain (lots, rolls, inspections, append-only inspection_events, projections) is
added in M1 (PLAN.md §4).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from threadeye.core.ids import uuid7
from threadeye.db.base import Base
from threadeye.security.rbac import Role

ROLE_VALUES = ", ".join(f"'{r.value}'" for r in Role)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(f"role IN ({ROLE_VALUES})", name="role_valid"),
        CheckConstraint("locale IN ('bn', 'en')", name="locale_valid"),
        CheckConstraint("digit_style IN ('latin', 'bengali')", name="digit_style_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    display_name: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(32))
    locale: Mapped[str] = mapped_column(String(2), default="bn", server_default="bn")
    digit_style: Mapped[str] = mapped_column(String(8), default="latin", server_default="latin")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuthSession(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(256))


class AuditLog(Base):
    """Append-only (DB triggers block UPDATE/DELETE/TRUNCATE) and SHA-256 hash-chained."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_action_entity_id", "action", "entity_id"),
        Index("ix_audit_log_at", "at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_role: Mapped[str | None] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(128))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class ComponentHeartbeat(Base):
    """Liveness of background components (worker) shown on the system status card."""

    __tablename__ = "component_heartbeats"

    component: Mapped[str] = mapped_column(String(32), primary_key=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    details: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
