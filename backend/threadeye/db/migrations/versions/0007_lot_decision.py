"""Lot decision: the supervisor's decision on a delivery, next to the computed lot verdict.

Revision ID: 0007_lot_decision
Revises: 0006_blob_storage
Create Date: 2026-10-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_lot_decision"
down_revision: str | None = "0006_blob_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "threadeye"


def upgrade() -> None:
    op.add_column("lots", sa.Column("decision", sa.String(length=32), nullable=True), schema=S)
    op.add_column("lots", sa.Column("decision_reason", sa.Text(), nullable=True), schema=S)
    op.add_column(
        "lots",
        sa.Column("decision_by", postgresql.UUID(as_uuid=True), sa.ForeignKey(f"{S}.users.id"), nullable=True),
        schema=S,
    )
    op.add_column("lots", sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True), schema=S)
    op.create_check_constraint(
        op.f("ck_lots_decision_valid"),
        "lots",
        "decision IS NULL OR decision IN ('ACCEPT', 'ACCEPT_WITH_REJECTS', 'REJECT', 'INSPECT_ALL')",
        schema=S,
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_lots_decision_valid"), "lots", schema=S)
    for col in ("decision_at", "decision_by", "decision_reason", "decision"):
        op.drop_column("lots", col, schema=S)
