"""Validated retrieval contracts and serializable result records."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any

from threadeye_evidence.corpus.safety import validate_relative_path

MAX_QUERY_CHARS = 1_000
MAX_RETRIEVAL_RESULTS = 20
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class RetrievalValidationError(ValueError):
    """A query, filter, mode, or retrieval configuration is unsafe or invalid."""


class RetrievalMode(str, Enum):
    KEYWORD = "keyword"
    VECTOR = "vector"
    HYBRID = "hybrid"


def validate_query(query: str) -> str:
    if not isinstance(query, str) or not query.strip():
        raise RetrievalValidationError("query must be a non-empty string")
    value = query.strip()
    if len(value) > MAX_QUERY_CHARS:
        raise RetrievalValidationError(f"query exceeds the {MAX_QUERY_CHARS}-character limit")
    value.encode("utf-8", errors="strict")
    return value


def validate_limit(value: int, *, field_name: str = "top_k") -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_RETRIEVAL_RESULTS:
        raise RetrievalValidationError(f"{field_name} must be from 1 through {MAX_RETRIEVAL_RESULTS}")
    return value


@dataclass(frozen=True)
class RetrievalFilters:
    corpus_id: str
    access_policy: str
    authorization_reference: str
    source_relative_path: str | None = None
    source_sha256: str | None = None
    corpus_version: str | None = None
    processing_version: str | None = None
    document_classification: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("corpus_id", "access_policy", "authorization_reference"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise RetrievalValidationError(f"{field_name} is a required authorization filter")
        if self.source_relative_path is not None:
            validate_relative_path(self.source_relative_path)
        for field_name in ("source_sha256", "corpus_version"):
            value = getattr(self, field_name)
            if value is not None and not _SHA256.fullmatch(value):
                raise RetrievalValidationError(f"{field_name} must be a lowercase SHA-256 digest")
        for field_name in ("processing_version", "document_classification"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise RetrievalValidationError(f"{field_name} must be a non-empty string when supplied")

    def to_mapping(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class EvidenceCandidate:
    chunk_id: str
    source_relative_path: str
    source_sha256: str
    chunk_sha256: str
    sanitized_text: str
    heading_hierarchy: tuple[str, ...]
    normalized_start: int
    normalized_end: int
    processing_version: str
    sanitization_status: str
    authorization_reference: str
    intended_use: str
    model_id: str
    model_revision: str
    profile_key: str
    corpus_version: str
    retrieval_corpus_id: str
    retrieval_access_policy: str
    document_classification: str
    keyword_score: float | None = None
    cosine_distance: float | None = None
    cosine_similarity: float | None = None

    @property
    def identity_signature(self) -> tuple[str, ...]:
        return (
            self.chunk_id,
            self.source_relative_path,
            self.source_sha256,
            self.chunk_sha256,
            self.profile_key,
            self.corpus_version,
            self.authorization_reference,
            self.retrieval_corpus_id,
            self.retrieval_access_policy,
        )


@dataclass(frozen=True)
class RankedEvidence:
    candidate: EvidenceCandidate
    final_rank: int
    retrieval_methods: tuple[str, ...]
    keyword_rank: int | None
    vector_rank: int | None
    rrf_score: float | None

    def to_mapping(self) -> dict[str, Any]:
        result = asdict(self.candidate)
        result["heading_hierarchy"] = list(self.candidate.heading_hierarchy)
        result.update(
            {
                "final_rank": self.final_rank,
                "retrieval_methods": list(self.retrieval_methods),
                "keyword_rank": self.keyword_rank,
                "vector_rank": self.vector_rank,
                "rrf_score": self.rrf_score,
            }
        )
        return result


@dataclass(frozen=True)
class RetrievalResponse:
    query: str
    mode: str
    top_k: int
    candidate_k: int
    filters: RetrievalFilters
    backend_status: dict[str, str]
    latency_ms: float
    results: tuple[RankedEvidence, ...]
    rrf_config: dict[str, float] | None = None

    def to_mapping(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "mode": self.mode,
            "top_k": self.top_k,
            "candidate_k": self.candidate_k,
            "filters": self.filters.to_mapping(),
            "backend_status": dict(self.backend_status),
            "latency_ms": self.latency_ms,
            "rrf_config": self.rrf_config,
            "result_count": len(self.results),
            "results": [result.to_mapping() for result in self.results],
        }
