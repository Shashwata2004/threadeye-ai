"""ORM models. M0 baseline: users, sessions, audit log, settings, component heartbeats.

The inspection domain (lots, rolls, inspections, append-only inspection_events, projections) is
added in M1 (PLAN.md §4).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    LargeBinary,
    Sequence,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
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


# ================================================================================================
# M1: receiving (master data, lots, rolls) and the inspection event store.
# ================================================================================================

ROLL_CODE_SEQ = Sequence("roll_code_seq", schema="threadeye", start=1)


class Supplier(Base):
    """A mill that ships fabric."""

    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    country: Mapped[str | None] = mapped_column(String(64))
    is_sample_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Buyer(Base):
    __tablename__ = "buyers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    is_sample_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RuleProfileRow(Base):
    """A versioned buyer rule profile. Immutable once active; edits create a new version."""

    __tablename__ = "rule_profiles"
    __table_args__ = (
        UniqueConstraint("name", "version", name="uq_rule_profiles_name_version"),
        CheckConstraint("status IN ('draft', 'active', 'retired')", name="status_valid"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("buyers.id"))
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(16), default="active", server_default="active")
    rules: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rules_hash: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Machine(Base):
    __tablename__ = "machines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    calibration: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lot(Base):
    """A delivery (challan) of rolls from one mill for one buyer."""

    __tablename__ = "lots"
    __table_args__ = (UniqueConstraint("supplier_id", "challan_no", name="uq_lots_supplier_id_challan_no"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    challan_no: Mapped[str] = mapped_column(String(64))
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), index=True)
    buyer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("buyers.id"), index=True)
    order_ref: Mapped[str | None] = mapped_column(String(64))
    fabric_type: Mapped[str] = mapped_column(String(128))
    colour: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[date] = mapped_column(Date)
    declared_rolls: Mapped[int] = mapped_column(Integer)
    declared_total_yd: Mapped[float | None] = mapped_column(Float)
    rule_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rule_profiles.id"))
    sampling_pct: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32), default="registered", server_default="registered")
    lot_verdict: Mapped[str | None] = mapped_column(String(32))
    is_sample_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Roll(Base):
    __tablename__ = "rolls"
    __table_args__ = (
        UniqueConstraint("lot_id", "mill_roll_no", name="uq_rolls_lot_id_mill_roll_no"),
        CheckConstraint(
            "status IN ('registered', 'in_inspection', 'inspected', 'on_hold', 'released', 'returned')",
            name="status_valid",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("lots.id"), index=True)
    roll_code: Mapped[str] = mapped_column(String(32), unique=True)
    mill_roll_no: Mapped[str] = mapped_column(String(64))
    dye_lot: Mapped[str | None] = mapped_column(String(64))
    declared_length_yd: Mapped[float] = mapped_column(Float)
    declared_width_in: Mapped[float] = mapped_column(Float)
    gsm: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(16), default="registered", server_default="registered")
    selected_for_inspection: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    label_printed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_sample_data: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Inspection(Base):
    """One inspection of one roll. Its history lives in inspection_events (append-only)."""

    __tablename__ = "inspections"
    __table_args__ = (
        CheckConstraint(
            "status IN ('created', 'running', 'paused', 'interrupted', 'completed', 'aborted')",
            name="status_valid",
        ),
        # One open inspection per roll (a finished or aborted one does not block a re-inspection).
        Index(
            "uq_inspections_open_roll",
            "roll_id",
            unique=True,
            postgresql_where=text("status IN ('created', 'running', 'paused', 'interrupted')"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    roll_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rolls.id"), index=True)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("machines.id"))
    inspector_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    rule_profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rule_profiles.id"))
    provider_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    source_descriptor: Mapped[dict[str, Any]] = mapped_column(JSONB)
    mode: Mapped[str] = mapped_column(String(16), default="demo", server_default="demo")
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    clock: Mapped[str] = mapped_column(String(16), default="browser", server_default="browser")
    status: Mapped[str] = mapped_column(String(16), default="created", server_default="created")
    checkpoint_frame: Mapped[int] = mapped_column(Integer, default=-1, server_default="-1")
    last_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # M2: live run, driver lease and verdict
    dataset_id: Mapped[str | None] = mapped_column(String(128))
    driver_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    driver_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    system_verdict: Mapped[str | None] = mapped_column(String(16))
    points_total: Mapped[int | None] = mapped_column(Integer)
    points_per_100: Mapped[float | None] = mapped_column(Float)
    yards_inspected: Mapped[float | None] = mapped_column(Float)
    final_verdict: Mapped[str | None] = mapped_column(String(24))
    decision_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class InspectionEvent(Base):
    """Append-only (DB triggers). The source of truth for an inspection; seq is gap-free per inspection."""

    __tablename__ = "inspection_events"
    __table_args__ = (UniqueConstraint("inspection_id", "seq", name="uq_inspection_events_inspection_id_seq"),)

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    inspection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inspections.id"))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(48))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actor_kind: Mapped[str] = mapped_column(String(16))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[str | None] = mapped_column(String(160), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")


class DefectRow(Base):
    """Projection of the de-duplicated defects of an inspection (rebuildable from the events)."""

    __tablename__ = "defects"
    __table_args__ = (UniqueConstraint("inspection_id", "defect_no", name="uq_defects_inspection_id_defect_no"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    inspection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inspections.id"))
    defect_no: Mapped[str] = mapped_column(String(16))
    origin: Mapped[str] = mapped_column(String(16))
    predicted_cls: Mapped[str] = mapped_column(String(64))
    current_cls: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(16))
    nondefect_category: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    start_yd: Mapped[float] = mapped_column(Float)
    end_yd: Mapped[float] = mapped_column(Float)
    center_yd: Mapped[float] = mapped_column(Float)
    across_start_cm: Mapped[float] = mapped_column(Float)
    across_end_cm: Mapped[float] = mapped_column(Float)
    length_in: Mapped[float] = mapped_column(Float)
    length_source: Mapped[str] = mapped_column(String(16))
    is_running: Mapped[bool] = mapped_column(Boolean)
    sightings: Mapped[int] = mapped_column(Integer)
    best_frame: Mapped[int] = mapped_column(Integer)
    points: Mapped[int | None] = mapped_column(Integer)
    explanation: Mapped[str | None] = mapped_column(Text)
    provider: Mapped[str | None] = mapped_column(String(64))
    # M2
    reject_reason: Mapped[str | None] = mapped_column(String(32))
    uncertain: Mapped[str | None] = mapped_column(String(32))
    is_continuous: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    excluded_reason: Mapped[str | None] = mapped_column(Text)
    points_reason: Mapped[str | None] = mapped_column(Text)
    first_frame: Mapped[int | None] = mapped_column(Integer)
    last_frame: Mapped[int | None] = mapped_column(Integer)
    best_bbox_px: Mapped[list[float] | None] = mapped_column(JSONB)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class InspectionFrame(Base):
    """Projection of sampled frames, plus the evidence images the browser captured (M2)."""

    __tablename__ = "inspection_frames"
    __table_args__ = (UniqueConstraint("inspection_id", "frame", name="uq_inspection_frames_inspection_id_frame"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid7)
    inspection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("inspections.id"), index=True)
    frame: Mapped[int] = mapped_column(Integer)
    top_yd: Mapped[float | None] = mapped_column(Float)
    bottom_yd: Mapped[float | None] = mapped_column(Float)
    hand_visible: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sample_reason: Mapped[str | None] = mapped_column(String(32))
    image_key: Mapped[str | None] = mapped_column(String(256))
    image_sha256: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    image_scale: Mapped[float | None] = mapped_column(Float)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Blob(Base):
    """Binary files (evidence photos) kept in the database itself on the cloud profile, so every
    teammate sharing the Supabase database sees them. The edge box keeps them on its local volume."""

    __tablename__ = "blobs"

    key: Mapped[str] = mapped_column(String(256), primary_key=True)
    data: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(64), default="image/jpeg", server_default="image/jpeg")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
