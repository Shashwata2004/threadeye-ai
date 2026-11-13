from __future__ import annotations

import anyio
import os
import unittest

from threadeye_evidence.mcp.database import ReadOnlyEvidenceDatabase
from threadeye_evidence.mcp.verify_client import verify_stdio


MCP_DSN = os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL")
RUN = (
    os.environ.get("THREADEYE_RUN_DB_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_MODEL_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_MCP_TESTS") == "1"
    and MCP_DSN
    and os.environ.get("THREADEYE_EVIDENCE_MCP_CONFIG")
    and os.environ.get("THREADEYE_EVIDENCE_MODEL_CACHE")
)


@unittest.skipUnless(RUN, "real MCP stdio/database integration not requested")
class MCPReadOnlyDatabaseIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database = ReadOnlyEvidenceDatabase.from_dsn(MCP_DSN)

    def test_identity_select_and_transaction_are_read_only(self) -> None:
        with self.database._connect() as connection:
            row = connection.execute(
                "select current_user as user, current_setting('transaction_read_only') as read_only, "
                "(select count(*)::integer from evidence_assistant.chunk_embeddings) as count"
            ).fetchone()
            role = connection.execute(
                "select rolsuper, rolcreatedb, rolcreaterole, rolinherit "
                "from pg_roles where rolname = current_user"
            ).fetchone()
        self.assertEqual(row["user"], "threadeye_evidence_mcp")
        self.assertEqual(row["read_only"], "on")
        self.assertGreater(row["count"], 0)
        self.assertEqual(role, {
            "rolsuper": False,
            "rolcreatedb": False,
            "rolcreaterole": False,
            "rolinherit": False,
        })

    def test_insert_update_delete_truncate_ddl_and_temp_are_denied(self) -> None:
        statements = (
            "insert into evidence_assistant.chunk_embeddings "
            "select * from evidence_assistant.chunk_embeddings where false",
            "update evidence_assistant.chunk_embeddings set sanitized_text=sanitized_text where false",
            "delete from evidence_assistant.chunk_embeddings where false",
            "truncate evidence_assistant.chunk_embeddings",
            "create table evidence_assistant.mcp_forbidden(id integer)",
            "create temporary table mcp_forbidden_temp(id integer)",
            "create role mcp_forbidden_role",
            "create database mcp_forbidden_database",
        )
        for statement in statements:
            with self.subTest(statement=statement), self.assertRaises(Exception):
                with self.database._connect() as connection:
                    connection.execute(statement)


@unittest.skipUnless(RUN, "real MCP stdio/database integration not requested")
class MCPStdioProtocolIntegrationTests(unittest.TestCase):
    def test_official_client_real_stdio_lifecycle_and_security(self) -> None:
        report = anyio.run(verify_stdio)
        self.assertTrue(report["initialization"]["capabilities_present"])
        self.assertEqual(report["initialization"]["server_name"], "threadeye-evidence")
        self.assertTrue(report["tool_allowlist_exact"])
        self.assertTrue(report["resource_allowlist_exact"])
        self.assertTrue(report["resource_read"]["read_only"])
        self.assertFalse(report["search"]["is_error"])
        self.assertEqual(report["search"]["source_paths"], ["technical-evidence.md"])
        self.assertEqual(report["answer"]["answer_mode"], "extractive")
        self.assertTrue(report["answer"]["citation_valid"])
        self.assertTrue(report["unsupported"]["answer_is_null"])
        self.assertTrue(report["unauthorized_scope_argument"]["rejected"])
        self.assertTrue(report["forbidden_tool"]["rejected"])
        self.assertIn("terminated", report["shutdown"])


if __name__ == "__main__":
    unittest.main()
