"""Verify a cloud_demo database: connectivity, schema isolation, append-only guards, audit chain.

Run with ``make cloud-check``. It reads the same settings the API uses, so it checks the connection
the app will actually make (Supavisor transaction mode), not a convenient substitute.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from threadeye.db.audit import verify_chain
from threadeye.db.base import SCHEMA
from threadeye.db.session import get_engine, get_sessionmaker
from threadeye.settings import get_settings

EXPECTED_TABLES = {"users", "sessions", "audit_log", "settings", "component_heartbeats"}
APPEND_ONLY_TABLES = {"audit_log"}
# Supabase exposes these to the public Data API (PostgREST/GraphQL). Ours must not be among them.
PUBLIC_API_ROLE = "authenticator"


@dataclass
class Report:
    checks: list[tuple[bool, str]] = field(default_factory=list)

    def add(self, ok: bool, message: str) -> None:
        self.checks.append((ok, message))

    @property
    def ok(self) -> bool:
        return all(ok for ok, _ in self.checks)

    def render(self) -> str:
        lines = [("  PASS " if ok else "  FAIL ") + msg for ok, msg in self.checks]
        lines.append("RESULT: " + ("OK" if self.ok else f"{sum(not ok for ok, _ in self.checks)} problem(s)"))
        return "\n".join(lines)


def _server_info(db: Session, report: Report) -> None:
    version = db.execute(text("SHOW server_version")).scalar_one()
    database = db.execute(text("SELECT current_database()")).scalar_one()
    user = db.execute(text("SELECT current_user")).scalar_one()
    report.add(True, f"connected: Postgres {version}, database {database}, user {user}")


def _tables(db: Session, report: Report) -> None:
    found = set(db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = :s"), {"s": SCHEMA}).all())
    missing = EXPECTED_TABLES - found
    report.add(
        not missing,
        f"schema {SCHEMA!r} has {len(found & EXPECTED_TABLES)}/{len(EXPECTED_TABLES)} tables"
        + (f"; missing: {', '.join(sorted(missing))} (run `make cloud-migrate`)" if missing else ""),
    )


def _append_only(db: Session, report: Report) -> None:
    for table in sorted(APPEND_ONLY_TABLES):
        triggers = set(
            db.scalars(
                text(
                    "SELECT tgname FROM pg_trigger t"
                    " JOIN pg_class c ON c.oid = t.tgrelid"
                    " JOIN pg_namespace n ON n.oid = c.relnamespace"
                    " WHERE n.nspname = :s AND c.relname = :t AND NOT t.tgisinternal"
                ),
                {"s": SCHEMA, "t": table},
            ).all()
        )
        report.add(len(triggers) >= 2, f"{table} is append-only ({len(triggers)} guard triggers)")


def _rls(db: Session, report: Report) -> None:
    unprotected = db.scalars(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace"
            " WHERE n.nspname = :s AND c.relkind = 'r' AND NOT c.relrowsecurity"
        ),
        {"s": SCHEMA},
    ).all()
    report.add(
        not unprotected,
        "row-level security is on for every table"
        if not unprotected
        else f"row-level security is OFF for: {', '.join(sorted(unprotected))}",
    )


def _data_api_exposure(db: Session, report: Report) -> None:
    """Supabase's Data API exposes only the schemas listed on the `authenticator` role."""
    settings = db.scalars(
        text(
            "SELECT unnest(s.setconfig) FROM pg_db_role_setting s"
            " JOIN pg_roles r ON r.oid = s.setrole WHERE r.rolname = :r"
        ),
        {"r": PUBLIC_API_ROLE},
    ).all()
    exposed = next(
        (v.split("=", 1)[1] for v in settings if v.startswith("pgrst.db_schemas=")),
        None,
    )
    if exposed is None:
        report.add(True, "no Supabase Data API on this database (nothing exposed)")
        return
    schemas = {s.strip() for s in exposed.split(",")}
    report.add(
        SCHEMA not in schemas,
        f"schema {SCHEMA!r} is NOT exposed to the public Data API (exposed: {exposed})"
        if SCHEMA not in schemas
        else f"schema {SCHEMA!r} IS EXPOSED to the public Data API: turn it off in"
        " Supabase → Settings → API → Exposed schemas",
    )


def _audit_chain(db: Session, report: Report) -> None:
    result = verify_chain(db)
    report.add(
        result.ok,
        f"audit chain intact ({result.checked} entries)"
        if result.ok
        else f"audit chain broken at #{result.first_bad_id}: {result.reason}",
    )


def run_cloud_check() -> Report:
    settings = get_settings()
    report = Report()
    report.add(True, f"profile: {settings.deploy_profile}")
    with get_sessionmaker()() as db:
        for check in (_server_info, _tables, _append_only, _rls, _data_api_exposure, _audit_chain):
            check(db, report)
    get_engine().dispose()
    return report
