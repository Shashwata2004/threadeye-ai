"""Isolated embedding and pgvector indexing for approved synthetic evidence."""

from threadeye_evidence.vector.embeddings import (
    BGE_MODEL_REVISION,
    EmbeddingMetadata,
    EmbeddingProvider,
    FastEmbedProvider,
    MockEmbeddingProvider,
)

__all__ = [
    "BGE_MODEL_REVISION",
    "EmbeddingMetadata",
    "EmbeddingProvider",
    "FastEmbedProvider",
    "MockEmbeddingProvider",
]
