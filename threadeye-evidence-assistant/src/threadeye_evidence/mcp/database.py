"""Least-privilege database role setup and read-only MCP connections."""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from urllib.parse import unquote, urlsplit

from threadeye_evidence.vector.database import (
    DatabaseSafetyError,
    DatabaseSettings,
    EXPECTED_DATABASE,
    _imports,
)


MCP_DATABASE_USER = "threadeye_evidence_mcp"
ADMIN_DATABASE_USER = "threadeye_evidence_admin"
MCP_STATEMENT_TIMEOUT_MS = 8_000
MCP_LOCK_TIMEOUT_MS = 2_000


class ReadOnlyEvidenceDatabase:
    """The narrow connection surface required by RetrievalStore, with no write methods."""

    def __init__(self, settings: DatabaseSettings) -> None:
        if settings.user != MCP_DATABASE_USER:
            raise DatabaseSafetyError("MCP database connection requires the dedicated read-only identity")
        self.settings = settings

    @classmethod
    def from_dsn(cls, dsn: str) -> "ReadOnlyEvidenceDatabase":
        return cls(DatabaseSettings.from_dsn(dsn, expected_user=MCP_DATABASE_USER))

    def _connect(self, *, register: bool = True) -> Any:
        psycopg, register_vector, dict_row = _imports()
        connection = psycopg.connect(
            self.settings.dsn,
            autocommit=False,
            connect_timeout=5,
            row_factory=dict_row,
            options=(
                f"-c default_transaction_read_only=on "
                f"-c statement_timeout={MCP_STATEMENT_TIMEOUT_MS} "
                f"-c lock_timeout={MCP_LOCK_TIMEOUT_MS}"
            ),
        )
        try:
            identity = connection.execute(
                "select current_database() as database, current_user as user, "
                "current_setting('transaction_read_only') as read_only"
            ).fetchone()
            if identity != {
                "database": EXPECTED_DATABASE,
                "user": MCP_DATABASE_USER,
                "read_only": "on",
            }:
                raise DatabaseSafetyError("MCP database identity or read-only transaction mode is invalid")
            if register:
                register_vector(connection)
            connection.commit()
            return connection
        except Exception:
            connection.close()
            raise


def setup_read_only_role(admin_dsn: str, mcp_dsn: str) -> dict[str, object]:
    """Operator-only idempotent setup; never called by the MCP server."""

    admin = DatabaseSettings.from_dsn(admin_dsn, expected_user=ADMIN_DATABASE_USER)
    mcp = DatabaseSettings.from_dsn(mcp_dsn, expected_user=MCP_DATABASE_USER)
    password = unquote(urlsplit(mcp.dsn).password or "")
    if not password:
        raise DatabaseSafetyError("MCP database password is missing")
    psycopg, _, dict_row = _imports()
    from psycopg import sql

    with psycopg.connect(admin.dsn, autocommit=False, connect_timeout=5, row_factory=dict_row) as connection:
        identity = connection.execute(
            "select current_database() as database, current_user as user"
        ).fetchone()
        if identity != {"database": EXPECTED_DATABASE, "user": ADMIN_DATABASE_USER}:
            raise DatabaseSafetyError("operator database identity is invalid")
        with connection.transaction():
            connection.execute(
                """
                do $setup$
                begin
                  if not exists (select 1 from pg_roles where rolname = 'threadeye_evidence_mcp') then
                    create role threadeye_evidence_mcp noinherit;
                  end if;
                end
                $setup$;
                """
            )
            role = sql.Identifier(MCP_DATABASE_USER)
            connection.execute(
                sql.SQL("alter role {} with login password {} nosuperuser nocreatedb nocreaterole noinherit").format(
                    role, sql.Literal(password)
                )
            )
            connection.execute(sql.SQL("alter role {} set default_transaction_read_only = on").format(role))
            connection.execute(sql.SQL("revoke all on database {} from {}").format(sql.Identifier(EXPECTED_DATABASE), role))
            connection.execute(sql.SQL("grant connect on database {} to {}").format(sql.Identifier(EXPECTED_DATABASE), role))
            connection.execute(sql.SQL("revoke all on schema public from {}").format(role))
            connection.execute(sql.SQL("revoke all on schema evidence_assistant from {}").format(role))
            connection.execute(sql.SQL("grant usage on schema evidence_assistant to {}").format(role))
            connection.execute(sql.SQL("revoke all on all tables in schema evidence_assistant from {}").format(role))
            connection.execute(sql.SQL("grant select on evidence_assistant.chunk_embeddings to {}").format(role))
            connection.execute(
                sql.SQL(
                    "alter default privileges for role threadeye_evidence in schema evidence_assistant "
                    "grant select on tables to {}"
                ).format(role)
            )
        privilege = connection.execute(
            """
            select has_table_privilege(%s, 'evidence_assistant.chunk_embeddings', 'select') as can_select,
                   has_table_privilege(%s, 'evidence_assistant.chunk_embeddings', 'insert') as can_insert,
                   has_table_privilege(%s, 'evidence_assistant.chunk_embeddings', 'update') as can_update,
                   has_table_privilege(%s, 'evidence_assistant.chunk_embeddings', 'delete') as can_delete
            """,
            (MCP_DATABASE_USER,) * 4,
        ).fetchone()
    return {
        "role": MCP_DATABASE_USER,
        "database": EXPECTED_DATABASE,
        "default_transaction_read_only": True,
        "privileges": dict(privilege),
    }


def setup_main() -> int:
    """Configure the local read-only role from environment-only credentials."""

    admin_dsn = os.environ.get("THREADEYE_EVIDENCE_ADMIN_DATABASE_URL")
    mcp_dsn = os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL")
    if not admin_dsn or not mcp_dsn:
        print("MCP database setup requires both trusted database URL environment variables", file=sys.stderr)
        return 2
    try:
        print(json.dumps(setup_read_only_role(admin_dsn, mcp_dsn), indent=2, sort_keys=True))
        return 0
    except Exception:
        print("MCP read-only role setup failed", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(setup_main())
