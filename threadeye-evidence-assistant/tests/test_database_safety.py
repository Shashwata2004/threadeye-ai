from __future__ import annotations

import unittest

from threadeye_evidence.vector.database import DatabaseSafetyError, DatabaseSettings


class DatabaseSafetyTests(unittest.TestCase):
    def test_exact_local_companion_identity_is_accepted(self) -> None:
        settings = DatabaseSettings.from_dsn(
            "postgresql://threadeye_evidence:local-test@127.0.0.1:55432/threadeye_evidence"
        )
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertEqual(settings.database, "threadeye_evidence")
        self.assertNotIn("local-test", repr(settings))

    def test_remote_or_production_hosts_are_rejected(self) -> None:
        for host in ("db.example.com", "project.supabase.co", "192.168.1.20"):
            with self.assertRaises(DatabaseSafetyError):
                DatabaseSettings.from_dsn(
                    f"postgresql://threadeye_evidence:secret@{host}:5432/threadeye_evidence"
                )

    def test_wrong_database_or_user_is_rejected(self) -> None:
        invalid = (
            "postgresql://postgres:secret@127.0.0.1:55432/threadeye_evidence",
            "postgresql://threadeye_evidence:secret@127.0.0.1:55432/postgres",
        )
        for dsn in invalid:
            with self.assertRaises(DatabaseSafetyError):
                DatabaseSettings.from_dsn(dsn)

    def test_missing_password_and_query_parameters_are_rejected(self) -> None:
        with self.assertRaises(DatabaseSafetyError):
            DatabaseSettings.from_dsn(
                "postgresql://threadeye_evidence@127.0.0.1:55432/threadeye_evidence"
            )
        with self.assertRaises(DatabaseSafetyError):
            DatabaseSettings.from_dsn(
                "postgresql://threadeye_evidence:x@127.0.0.1:55432/threadeye_evidence?sslmode=disable"
            )
