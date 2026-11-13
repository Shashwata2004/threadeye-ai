from __future__ import annotations

import os
import unittest
from pathlib import Path

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.corpus.allowlist import load_manifest
from threadeye_evidence.corpus.chunking import ChunkConfig
from threadeye_evidence.corpus.ingestion import ingest_document
from threadeye_evidence.qa.evaluation import evaluate_qa_holdout, load_qa_holdout
from threadeye_evidence.retrieval.engine import HybridRetriever
from threadeye_evidence.retrieval.models import RetrievalFilters
from threadeye_evidence.retrieval.policy import SYNTHETIC_EVALUATION_POLICY
from threadeye_evidence.retrieval.store import RetrievalStore
from threadeye_evidence.vector.database import DatabaseSettings, EvidenceDatabase
from threadeye_evidence.vector.embeddings import FastEmbedProvider
from threadeye_evidence.vector.indexing import default_migrations_dir, index_ingestion_result


ROOT = Path(__file__).resolve().parents[1]
DATABASE_URL = os.environ.get("THREADEYE_EVIDENCE_DATABASE_URL")
RUN = os.environ.get("THREADEYE_RUN_DB_TESTS") == "1" and os.environ.get("THREADEYE_RUN_MODEL_TESTS") == "1" and DATABASE_URL


@unittest.skipUnless(RUN, "independent QA holdout integration not requested")
class RealQAHoldoutIntegrationTests(unittest.TestCase):
    def test_fixed_holdout_reports_real_outcomes_without_threshold_tuning(self) -> None:
        provider = FastEmbedProvider(ROOT / "build/model-cache", local_files_only=True)
        database = EvidenceDatabase(DatabaseSettings.from_dsn(DATABASE_URL), migrations_dir=default_migrations_dir())
        database.migrate()
        manifest = load_manifest(ROOT / "knowledge/synthetic-manifest.json")
        ingestion = ingest_document(
            ROOT / "examples/synthetic", manifest, "technical-evidence.md",
            intended_use="prompt04_synthetic_vector_index",
            chunk_config=ChunkConfig(target_chars=300, max_chars=600),
        )
        index_ingestion_result(
            ingestion, provider, database, batch_size=4, retrieval_policy=SYNTHETIC_EVALUATION_POLICY,
        )
        historical = tuple(ROOT / "evaluation" / name for name in (
            "retrieval-v1.json", "answering-v1.json", "security-v1.json",
        ))
        dataset = load_qa_holdout(ROOT / "evaluation/qa-holdout-v1.json", historical_paths=historical)
        filters = RetrievalFilters(
            SYNTHETIC_EVALUATION_POLICY.corpus_id,
            SYNTHETIC_EVALUATION_POLICY.access_policy,
            "PROMPT-04-SYNTHETIC-VECTOR-FIXTURE",
            document_classification=SYNTHETIC_EVALUATION_POLICY.document_classification,
        )
        engine = EvidenceAnswerEngine(HybridRetriever(RetrievalStore(database), provider))
        report = evaluate_qa_holdout(dataset, engine, filters, command="unittest fixed Prompt 11 QA holdout")
        metrics = report["metrics"]
        self.assertEqual(metrics["cases"], 10)
        self.assertEqual(metrics["runtime_failures"], 0)
        self.assertEqual(metrics["unsupported_claims"], 0)
        self.assertEqual(metrics["citation_validity"]["numerator"], metrics["citation_validity"]["denominator"])
        self.assertFalse(report["threshold_tuning_permitted"])
        self.assertEqual(report["human_review"]["completed_cases"], 0)


if __name__ == "__main__":
    unittest.main()
