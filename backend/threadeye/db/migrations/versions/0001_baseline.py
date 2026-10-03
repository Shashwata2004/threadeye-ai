"""M0 baseline: users, sessions, append-only hash-chained audit log, settings, heartbeats.

Revision ID: 0001_baseline
Revises:
Create Date: 2026-10-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "threadeye"
ROLES = "'inspector', 'qc_supervisor', 'store_incharge', 'cutting_master', 'merchandiser', 'management', 'admin'"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("locale", sa.String(2), server_default="bn", nullable=False),
        sa.Column("digit_style", sa.String(8), server_default="latin", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"role IN ({ROLES})", name="ck_users_role_valid"),
        sa.CheckConstraint("locale IN ('bn', 'en')", name="ck_users_locale_valid"),
        sa.CheckConstraint("digit_style IN ('latin', 'bengali')", name="ck_users_digit_style_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        schema=S,
    )
    op.create_table(
        "sessions",
        sa.Column("id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", pg.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(256), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], [f"{S}.users.id"], name="fk_sessions_user_id_users", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
        schema=S,
    )
    op.create_index("ix_sessions_user_id", "sessions", ["user_id"], schema=S)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_user_id", pg.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(32), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=True),
        sa.Column("entity_id", sa.String(128), nullable=True),
        sa.Column("before", pg.JSONB(), nullable=True),
        sa.Column("after", pg.JSONB(), nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("prev_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_audit_log"),
        sa.UniqueConstraint("hash", name="uq_audit_log_hash"),
        schema=S,
    )
    op.create_index("ix_audit_log_action_entity_id", "audit_log", ["action", "entity_id"], schema=S)
    op.create_index("ix_audit_log_at", "audit_log", ["at"], schema=S)

    op.create_table(
        "settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", pg.JSONB(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_by", pg.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("key", name="pk_settings"),
        schema=S,
    )
    op.create_table(
        "component_heartbeats",
        sa.Column("component", sa.String(32), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", pg.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("component", name="pk_component_heartbeats"),
        schema=S,
    )

    # Append-only enforcement, reused by inspection_events from M1.
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION {S}.forbid_mutation() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'append-only table %: % is not allowed', TG_TABLE_NAME, TG_OP
            USING ERRCODE = 'insufficient_privilege';
        END
        $$;
        """
    )
    op.execute(
        f"CREATE TRIGGER audit_log_no_update_delete BEFORE UPDATE OR DELETE ON {S}.audit_log "
        f"FOR EACH ROW EXECUTE FUNCTION {S}.forbid_mutation();"
    )
    op.execute(
        f"CREATE TRIGGER audit_log_no_truncate BEFORE TRUNCATE ON {S}.audit_log "
        f"FOR EACH STATEMENT EXECUTE FUNCTION {S}.forbid_mutation();"
    )


def downgrade() -> None:
    op.execute(f"DROP TRIGGER IF EXISTS audit_log_no_truncate ON {S}.audit_log")
    op.execute(f"DROP TRIGGER IF EXISTS audit_log_no_update_delete ON {S}.audit_log")
    op.execute(f"DROP FUNCTION IF EXISTS {S}.forbid_mutation()")
    op.drop_table("component_heartbeats", schema=S)
    op.drop_table("settings", schema=S)
    op.drop_index("ix_audit_log_at", table_name="audit_log", schema=S)
    op.drop_index("ix_audit_log_action_entity_id", table_name="audit_log", schema=S)
    op.drop_table("audit_log", schema=S)
    op.drop_index("ix_sessions_user_id", table_name="sessions", schema=S)
    op.drop_table("sessions", schema=S)
    op.drop_table("users", schema=S)
