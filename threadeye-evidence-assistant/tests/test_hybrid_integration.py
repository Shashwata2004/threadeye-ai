from __future__ import annotations

import os
import unittest

from threadeye_evidence.retrieval.engine import HybridRetriever
from threadeye_evidence.retrieval.models import RetrievalFilters, RetrievalMode
from threadeye_evidence.retrieval.policy import DENY_RETRIEVAL_POLICY, RetrievalAccessPolicy
from threadeye_evidence.retrieval.store import RetrievalStore
from threadeye_evidence.vector.database import DatabaseSettings, EvidenceDatabase
from threadeye_evidence.vector.embeddings import MockEmbeddingProvider
from threadeye_evidence.vector.indexing import default_migrations_dir, index_ingestion_result

from vector_helpers import synthetic_result


DATABASE_URL = os.environ.get("THREADEYE_EVIDENCE_DATABASE_URL")
RUN = os.environ.get("THREADEYE_RUN_DB_TESTS") == "1" and DATABASE_URL
POLICY = RetrievalAccessPolicy("prompt05-integration-corpus", "prompt05-test-only", "synthetic_test_fixture", True)
FILTERS = RetrievalFilters(POLICY.corpus_id, POLICY.access_policy, "PROMPT-04-TEST")


@unittest.skipUnless(RUN, "isolated pgvector not requested")
class HybridRetrievalIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database = EvidenceDatabase(DatabaseSettings.from_dsn(DATABASE_URL), migrations_dir=default_migrations_dir())
        cls.database.migrate()
        cls.provider = MockEmbeddingProvider(384)
        cls.store = RetrievalStore(cls.database)
        cls.retriever = HybridRetriever(cls.store, cls.provider)
        cls.result = synthetic_result(
            "# Fictional Retrieval\n\n## Receiving Evidence\n\nIdentifier ROLL-TEST-55 enters the quarantine lane before visual inspection.\n\n"
            "## Supervisor Evidence\n\nA fictional supervisor confirms or rejects the defect classification and records a traceable reason.\n",
            relative_path="prompt05-authorized.md",
        )
        index_ingestion_result(cls.result, cls.provider, cls.database, retrieval_policy=POLICY)
        denied = synthetic_result(
            "# Private Synthetic\n\n## Hidden\n\nFORBIDDEN-LEXEME must never be served.\n",
            relative_path="prompt05-denied.md",
        )
        index_ingestion_result(denied, cls.provider, cls.database, retrieval_policy=DENY_RETRIEVAL_POLICY)

    def test_full_text_generated_column_and_gin_index_exist(self) -> None:
        with self.database._connect() as connection:
            column = connection.execute(
                "select data_type, is_generated from information_schema.columns where table_schema='evidence_assistant' and table_name='chunk_embeddings' and column_name='search_vector'"
            ).fetchone()
            index = connection.execute(
                "select indexdef from pg_indexes where schemaname='evidence_assistant' and indexname='chunk_embeddings_search_vector_idx'"
            ).fetchone()
        self.assertEqual(column, {"data_type": "tsvector", "is_generated": "ALWAYS"})
        self.assertIn("USING gin", index["indexdef"])

    def test_keyword_phrase_ranking_and_provenance(self) -> None:
        results = self.store.keyword_search('"quarantine lane"', self.provider.metadata, FILTERS, top_k=5)
        self.assertTrue(results)
        self.assertEqual(results[0].source_sha256, self.result.source_sha256)
        self.assertIn("Receiving Evidence", results[0].heading_hierarchy)
        self.assertGreater(results[0].keyword_score, 0)

    def test_zero_keyword_result_and_sql_injection_are_safe(self) -> None:
        self.assertEqual(self.store.keyword_search("zzznomatchqqq", self.provider.metadata, FILTERS, top_k=5), [])
        self.assertEqual(self.store.keyword_search("'; drop table evidence_assistant.chunk_embeddings; --", self.provider.metadata, FILTERS, top_k=5), [])
        with self.database._connect() as connection:
            relation = connection.execute("select to_regclass('evidence_assistant.chunk_embeddings') as name").fetchone()
        self.assertIsNotNone(relation["name"])

    def test_authorization_filters_apply_before_both_rankings(self) -> None:
        lexical = self.store.keyword_search("FORBIDDEN-LEXEME", self.provider.metadata, FILTERS, top_k=5)
        semantic = self.store.vector_search(self.provider.embed_query("FORBIDDEN-LEXEME"), self.provider.metadata, FILTERS, top_k=20)
        self.assertEqual(lexical, [])
        self.assertNotIn("prompt05-denied.md", {item.source_relative_path for item in semantic})
        wrong = RetrievalFilters("wrong-corpus", POLICY.access_policy, "PROMPT-04-TEST")
        self.assertEqual(self.store.keyword_search("supervisor", self.provider.metadata, wrong, top_k=5), [])
        self.assertEqual(self.store.vector_search(self.provider.embed_query("supervisor"), self.provider.metadata, wrong, top_k=5), [])

    def test_optional_source_filter_is_exact(self) -> None:
        allowed = RetrievalFilters(POLICY.corpus_id, POLICY.access_policy, "PROMPT-04-TEST", source_relative_path="prompt05-authorized.md")
        rejected = RetrievalFilters(POLICY.corpus_id, POLICY.access_policy, "PROMPT-04-TEST", source_relative_path="different.md")
        self.assertTrue(self.store.keyword_search("supervisor", self.provider.metadata, allowed, top_k=5))
        self.assertEqual(self.store.keyword_search("supervisor", self.provider.metadata, rejected, top_k=5), [])

    def test_hybrid_executes_both_branches_and_fuses(self) -> None:
        response = self.retriever.search("supervisor classification reason", mode=RetrievalMode.HYBRID, filters=FILTERS, top_k=2)
        self.assertIn("keyword", response.backend_status)
        self.assertIn("vector", response.backend_status)
        self.assertTrue(response.results)
        self.assertIsNotNone(response.results[0].rrf_score)
        self.assertEqual(response.results[0].candidate.retrieval_corpus_id, POLICY.corpus_id)

    def test_modes_are_clearly_differentiated(self) -> None:
        keyword = self.retriever.search("supervisor", mode="keyword", filters=FILTERS, top_k=1)
        vector = self.retriever.search("human checks a proposed flaw label", mode="vector", filters=FILTERS, top_k=1)
        self.assertEqual(keyword.results[0].retrieval_methods, ("keyword",))
        self.assertEqual(vector.results[0].retrieval_methods, ("vector",))

    def test_cross_model_profile_fails_closed(self) -> None:
        other = MockEmbeddingProvider(384, revision="different")
        with self.assertRaisesRegex(Exception, "vector retrieval failed"):
            HybridRetriever(self.store, other).search("supervisor", mode="vector", filters=FILTERS)

    def test_explain_plan_is_real_and_reports_actual_node(self) -> None:
        plan = self.store.keyword_plan("supervisor", self.provider.metadata, FILTERS)
        self.assertIn("Plan", plan)
        self.assertIn("Execution Time", plan)


if __name__ == "__main__":
    unittest.main()
