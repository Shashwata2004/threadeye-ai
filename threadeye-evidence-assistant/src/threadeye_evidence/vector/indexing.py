"""Embedding, indexing, and exact-vector-query orchestration."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

from threadeye_evidence.corpus.ingestion import IngestionResult
from threadeye_evidence.vector.database import EvidenceDatabase, IndexReport, SearchResult
from threadeye_evidence.vector.embeddings import EmbeddingProvider
from threadeye_evidence.vector.provenance import approved_chunk_batch


def corpus_version(result: IngestionResult, provider: EmbeddingProvider) -> str:
    identity = [
        result.source_relative_path,
        result.source_sha256,
        result.normalized_sha256,
        result.approval_reference,
        result.intended_use,
        result.processing_version,
        provider.metadata.profile_key,
    ]
    identity.extend(chunk.chunk_id for chunk in result.chunks)
    return hashlib.sha256("\0".join(identity).encode("utf-8")).hexdigest()


def index_ingestion_result(
    result: IngestionResult,
    provider: EmbeddingProvider,
    database: EvidenceDatabase,
    *,
    batch_size: int = 32,
) -> IndexReport:
    batch = approved_chunk_batch(result)
    vectors = provider.embed_documents([chunk.content for chunk in batch.chunks], batch_size=batch_size)
    run_id = f"idx-{secrets.token_hex(12)}"
    return database.index_batch(
        batch,
        vectors,
        provider.metadata,
        run_id=run_id,
        corpus_version=corpus_version(result, provider),
    )


def vector_query(
    query: str,
    provider: EmbeddingProvider,
    database: EvidenceDatabase,
    *,
    top_k: int = 5,
) -> list[SearchResult]:
    vector = provider.embed_query(query)
    return database.search(vector, provider.metadata, top_k=top_k)


def default_migrations_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "migrations"
