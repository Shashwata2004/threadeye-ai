from __future__ import annotations

import math
import os
import unittest
from pathlib import Path

from threadeye_evidence.corpus.allowlist import load_manifest
from threadeye_evidence.corpus.chunking import ChunkConfig
from threadeye_evidence.corpus.ingestion import ingest_document
from threadeye_evidence.vector.database import DatabaseSettings, EvidenceDatabase
from threadeye_evidence.vector.embeddings import BGE_MODEL_REVISION, FastEmbedProvider
from threadeye_evidence.vector.indexing import default_migrations_dir, index_ingestion_result, vector_query


ROOT = Path(__file__).resolve().parents[1]
RUN_MODEL = os.environ.get("THREADEYE_RUN_MODEL_TESTS") == "1"
RUN_DATABASE = os.environ.get("THREADEYE_RUN_DB_TESTS") == "1"
DATABASE_URL = os.environ.get("THREADEYE_EVIDENCE_DATABASE_URL")


@unittest.skipUnless(RUN_MODEL, "genuine local model not requested")
class RealEmbeddingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.provider = FastEmbedProvider(ROOT / "build" / "model-cache", local_files_only=True)

    def test_real_model_dimension_finite_values_batch_and_repeatability(self) -> None:
        texts = ["synthetic fabric receiving", "fictional supervisor review"]
        first = self.provider.embed_documents(texts, batch_size=2)
        second = self.provider.embed_documents(texts, batch_size=1)
        self.assertEqual([len(vector) for vector in first], [384, 384])
        self.assertTrue(all(math.isfinite(value) for vector in first for value in vector))
        for left, right in zip(first, second):
            self.assertTrue(all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-7) for a, b in zip(left, right)))

    def test_runtime_is_cpu_and_exact_revision_is_cached(self) -> None:
        runtime = self.provider.runtime_info()
        self.assertEqual(runtime["execution_providers"], ["CPUExecutionProvider"])
        snapshots = list((ROOT / "build" / "model-cache").glob("models--Qdrant--bge-small-en-v1.5-onnx-Q/snapshots/*"))
        self.assertIn(BGE_MODEL_REVISION, {path.name for path in snapshots})

    @unittest.skipUnless(RUN_DATABASE and DATABASE_URL, "isolated pgvector not requested")
    def test_real_embedding_insert_and_retrieval_with_provenance(self) -> None:
        manifest = load_manifest(ROOT / "knowledge" / "synthetic-manifest.json")
        result = ingest_document(
            ROOT / "examples" / "synthetic",
            manifest,
            "technical-evidence.md",
            intended_use="prompt04_synthetic_vector_index",
            chunk_config=ChunkConfig(target_chars=300, max_chars=600),
        )
        database = EvidenceDatabase(DatabaseSettings.from_dsn(DATABASE_URL), migrations_dir=default_migrations_dir())
        database.migrate()
        report = index_ingestion_result(result, self.provider, database, batch_size=4)
        matches = vector_query(
            "Who reviews flagged defect classifications and records a reason?",
            self.provider,
            database,
            top_k=3,
        )
        self.assertGreater(report.chunk_count, 0)
        self.assertTrue(matches)
        self.assertEqual(matches[0].source_relative_path, "technical-evidence.md")
        self.assertEqual(matches[0].authorization_reference, "PROMPT-04-SYNTHETIC-VECTOR-FIXTURE")
        self.assertIn("Supervisor Review", matches[0].heading_hierarchy)
