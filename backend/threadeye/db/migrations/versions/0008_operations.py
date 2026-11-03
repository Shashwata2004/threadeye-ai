"""Durable operations, cutting approvals and measured roll dimensions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0008_operations"
down_revision: str | None = "0007_lot_decision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
S = "threadeye"


def upgrade() -> None:
    for name in ("measured_length_yd", "measured_width_in"):
        op.add_column("inspections", sa.Column(name, sa.Float(), nullable=True), schema=S)
    op.create_table(
        "operation_runs",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("actor_id", UUID(), sa.ForeignKey(f"{S}.users.id"), nullable=False),
        sa.Column("machine_id", UUID(), sa.ForeignKey(f"{S}.machines.id")),
        sa.Column("inspection_id", UUID(), sa.ForeignKey(f"{S}.inspections.id")),
        sa.Column("inputs", JSONB(), nullable=False),
        sa.Column("result", JSONB()),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        schema=S,
    )
    op.create_index("ix_threadeye_operation_runs_kind", "operation_runs", ["kind"], schema=S)
    op.create_table(
        "cutting_plans",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("inspection_id", UUID(), sa.ForeignKey(f"{S}.inspections.id"), unique=True, nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=False),
        sa.Column("plan", JSONB(), nullable=False),
        sa.Column("approved_by", UUID(), sa.ForeignKey(f"{S}.users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_by", UUID(), sa.ForeignKey(f"{S}.users.id")),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        schema=S,
    )
    for name in ("operation_runs", "cutting_plans"):
        op.execute(f"ALTER TABLE {S}.{name} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    op.drop_table("cutting_plans", schema=S)
    op.drop_table("operation_runs", schema=S)
    for name in ("measured_length_yd", "measured_width_in"):
        op.drop_column("inspections", name, schema=S)
