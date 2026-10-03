"""Enable row-level security on every ThreadEye table (defence in depth).

Our tables live in the ``threadeye`` schema, which Supabase does not expose to its public Data API.
RLS is the second layer: if the schema is ever exposed by mistake, anonymous roles still read
nothing, because RLS is on and no policy grants access. The application connects as the table
owner, which bypasses RLS, so behaviour is unchanged on both profiles.

Revision ID: 0002_rls
Revises: 0001_baseline
Create Date: 2026-10-03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_rls"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

S = "threadeye"
# alembic_version is Alembic's own bookkeeping, but it lives in our schema, so it is covered too.
TABLES = ("users", "sessions", "audit_log", "settings", "component_heartbeats", "alembic_version")
# Supabase's public API roles. They do not exist on the edge profile, hence the IF EXISTS guard.
REVOKE_FROM_PUBLIC_ROLES = """
DO $$
DECLARE target text;
BEGIN
  FOREACH target IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = target) THEN
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I', 'threadeye', target);
      EXECUTE format('REVOKE ALL ON SCHEMA %I FROM %I', 'threadeye', target);
    END IF;
  END LOOP;
END
$$;
"""


def upgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {S}.{table} ENABLE ROW LEVEL SECURITY")
    # One static statement: the role names are a SQL array, not Python interpolation.
    op.execute(REVOKE_FROM_PUBLIC_ROLES)


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"ALTER TABLE {S}.{table} DISABLE ROW LEVEL SECURITY")
