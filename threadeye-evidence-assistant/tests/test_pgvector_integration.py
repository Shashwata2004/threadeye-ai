from __future__ import annotations

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from threadeye_evidence.vector.database import DatabaseSettings, EvidenceDatabase, IndexingConflictError
from threadeye_evidence.vector.embeddings import MockEmbeddingProvider
from threadeye_evidence.vector.indexing import default_migrations_dir, index_ingestion_result, vector_query

from vector_helpers import synthetic_result


DATABASE_URL = os.environ.get("THREADEYE_EVIDENCE_DATABASE_URL")


@unittest.skipUnless(os.environ.get("THREADEYE_RUN_DB_TESTS") == "1" and DATABASE_URL, "isolated pgvector not requested")
class PgvectorIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database = EvidenceDatabase(DatabaseSettings.from_dsn(DATABASE_URL), migrations_dir=default_migrations_dir())
        cls.database.migrate()
        cls.provider = MockEmbeddingProvider(384)

    def test_extension_migration_and_vector_column(self) -> None:
        with self.database._connect() as connection:
            extension = connection.execute(
                "select extversion from pg_extension where extname = 'vector'"
            ).fetchone()
            column = connection.execute(
                """
                select format_type(a.atttypid, a.atttypmod) as type
                from pg_attribute a
                where a.attrelid = 'evidence_assistant.chunk_embeddings'::regclass
                  and a.attname = 'embedding'
                """
            ).fetchone()
        self.assertIsNotNone(extension)
        self.assertEqual(column["type"], "vector(384)")

    def test_concurrent_migrations_are_serialized(self) -> None:
        def migrate() -> list[str]:
            database = EvidenceDatabase(
                DatabaseSettings.from_dsn(DATABASE_URL), migrations_dir=default_migrations_dir()
            )
            return database.migrate()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: migrate(), range(2)))
        self.assertEqual(results, [["001_evidence_vectors.sql"], ["001_evidence_vectors.sql"]])

    def test_insert_upsert_and_repeated_indexing_do_not_duplicate(self) -> None:
        result = synthetic_result(relative_path="idempotent.md")
        first = index_ingestion_result(result, self.provider, self.database)
        second = index_ingestion_result(result, self.provider, self.database)
        self.assertEqual(first.chunk_count, len(result.chunks))
        self.assertEqual(second.inserted, 0)
        self.assertEqual(second.updated, len(result.chunks))
        with self.database._connect() as connection:
            count = connection.execute(
                """
                select count(*)::integer as count
                from evidence_assistant.chunk_embeddings
                where profile_key = %s and source_relative_path = %s
                """,
                (self.provider.metadata.profile_key, "idempotent.md"),
            ).fetchone()["count"]
        self.assertEqual(count, len(result.chunks))

    def test_changed_document_removes_stale_chunks(self) -> None:
        first = synthetic_result(
            "# Fictional\n\n## Receiving\n\nA synthetic receiving inspection record.\n",
            relative_path="changed.md",
        )
        second = synthetic_result(
            "# Fictional\n\n## Review\n\nA changed synthetic supervisor review record with a new content hash.\n",
            relative_path="changed.md",
        )
        index_ingestion_result(first, self.provider, self.database)
        report = index_ingestion_result(second, self.provider, self.database)
        self.assertTrue(report.source_changed)
        self.assertGreaterEqual(report.removed, 1)

    def test_dimension_mismatch_is_rejected(self) -> None:
        result = synthetic_result(relative_path="dimension.md")
        small = MockEmbeddingProvider(8)
        with self.assertRaisesRegex(IndexingConflictError, "384"):
            index_ingestion_result(result, small, self.database)

    def test_cosine_search_preserves_source_metadata(self) -> None:
        result = synthetic_result(relative_path="search.md")
        index_ingestion_result(result, self.provider, self.database)
        matches = vector_query("fictional supervisor review", self.provider, self.database, top_k=20)
        self.assertTrue(matches)
        match = next(item for item in matches if item.source_relative_path == "search.md")
        self.assertEqual(match.source_sha256, result.source_sha256)
        self.assertEqual(match.model_revision, self.provider.metadata.model_revision)
        self.assertGreaterEqual(match.cosine_similarity, -1.0)
        self.assertLessEqual(match.cosine_similarity, 1.0)

    def test_model_profiles_are_never_mixed(self) -> None:
        result = synthetic_result(relative_path="profile.md")
        index_ingestion_result(result, self.provider, self.database)
        other = MockEmbeddingProvider(384, revision="incompatible-revision")
        with self.assertRaisesRegex(IndexingConflictError, "controlled re-embedding"):
            vector_query("synthetic", other, self.database, top_k=5)

    def test_failed_transaction_rolls_back(self) -> None:
        self.assertTrue(self.database.execute_rollback_probe())

    def test_status_confirms_isolated_database(self) -> None:
        status = self.database.status(self.provider.metadata)
        self.assertEqual(status["database"], "threadeye_evidence")
        self.assertIsNotNone(status["pgvector_version"])
        self.assertEqual(status["search_strategy"], "exact_cosine_sequential_scan")
        with self.database._connect() as connection:
            role = connection.execute(
                "select rolsuper, rolcreatedb, rolcreaterole from pg_roles where rolname = current_user"
            ).fetchone()
        self.assertEqual(role, {"rolsuper": False, "rolcreatedb": False, "rolcreaterole": False})
