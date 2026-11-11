"""Typed contracts for evidence answers, citations, and sufficiency decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    UNAUTHORIZED = "unauthorized"
    UNSUPPORTED_REQUEST = "unsupported_request"
    RETRIEVAL_ERROR = "retrieval_error"
    CITATION_VALIDATION_FAILED = "citation_validation_failed"


class AbstentionReason(str, Enum):
    AMBIGUOUS_QUESTION = "ambiguous_question"
    AUTHORIZATION_SCOPE_EMPTY = "authorization_scope_empty"
    CONTRADICTORY_EVIDENCE = "contradictory_evidence"
    INSUFFICIENT_RELEVANCE = "insufficient_relevance"
    INVALID_CITATION = "invalid_citation"
    NO_EVIDENCE = "no_evidence"
    PROMPT_INJECTION_REQUEST = "prompt_injection_request"
    PRODUCTION_ACCESS_REQUEST = "production_access_request"
    RETRIEVAL_BACKEND_FAILURE = "retrieval_backend_failure"
    SECRET_EXFILTRATION_REQUEST = "secret_exfiltration_request"
    UNTRUSTED_INSTRUCTION_EVIDENCE = "untrusted_instruction_evidence"
    VERDICT_OVERRIDE_REQUEST = "verdict_override_request"


@dataclass(frozen=True)
class EvidenceCitation:
    source_relative_path: str
    source_sha256: str
    chunk_id: str
    chunk_sha256: str
    heading_hierarchy: tuple[str, ...]
    normalized_start: int
    normalized_end: int
    processing_version: str
    authorization_reference: str
    corpus_version: str
    excerpt: str

    def to_mapping(self) -> dict[str, Any]:
        result = asdict(self)
        result["heading_hierarchy"] = list(self.heading_hierarchy)
        return result


@dataclass(frozen=True)
class SufficiencyDecision:
    sufficient: bool
    reason: str | None
    supporting_chunk_ids: tuple[str, ...]
    signals: dict[str, Any]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "sufficient": self.sufficient,
            "reason": self.reason,
            "supporting_chunk_ids": list(self.supporting_chunk_ids),
            "signals": dict(self.signals),
        }


@dataclass(frozen=True)
class EvidenceAnswer:
    question: str
    status: str
    answer_mode: str
    answer: str | None
    citations: tuple[EvidenceCitation, ...]
    supporting_chunk_ids: tuple[str, ...]
    retrieval_mode: str
    retrieval_metadata: dict[str, Any]
    abstention_reason: str | None
    limitations: tuple[str, ...]
    corpus_id: str
    model_profile: dict[str, Any]
    processing_versions: tuple[str, ...]
    sufficiency: SufficiencyDecision | None
    latency_ms: float

    def to_mapping(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "status": self.status,
            "answer_mode": self.answer_mode,
            "answer": self.answer,
            "citations": [citation.to_mapping() for citation in self.citations],
            "supporting_chunk_ids": list(self.supporting_chunk_ids),
            "retrieval_mode": self.retrieval_mode,
            "retrieval_metadata": dict(self.retrieval_metadata),
            "abstention_reason": self.abstention_reason,
            "limitations": list(self.limitations),
            "corpus_id": self.corpus_id,
            "model_profile": dict(self.model_profile),
            "processing_versions": list(self.processing_versions),
            "sufficiency": self.sufficiency.to_mapping() if self.sufficiency else None,
            "latency_ms": self.latency_ms,
        }
