"""Store blob data uncompressed out of line, so a slice of a large file is read without the rest

Videos are served in pieces (Range requests). With EXTERNAL storage Postgres reads only the
requested slice of a value; the default (EXTENDED) may compress it, and then every slice needs the
whole value decompressed. Photos and videos are already compressed, so nothing is lost.

Revision ID: 0006_blob_storage
Revises: 0005_blobs
Create Date: 2026-10-06
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006_blob_storage"
down_revision: str | None = "0005_blobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE threadeye.blobs ALTER COLUMN data SET STORAGE EXTERNAL")


def downgrade() -> None:
    op.execute("ALTER TABLE threadeye.blobs ALTER COLUMN data SET STORAGE EXTENDED")
