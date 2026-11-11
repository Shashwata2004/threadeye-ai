"""Exact citation construction and claim-support validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from threadeye_evidence.answering.abstention import SufficiencyConfig, content_tokens
from threadeye_evidence.answering.models import EvidenceCitation
from threadeye_evidence.retrieval.models import RankedEvidence, RetrievalFilters


class CitationValidationError(ValueError):
    """A citation is absent, spoofed, unauthorized, or does not support the answer."""


def citation_from_excerpt(evidence: RankedEvidence, excerpt: str) -> EvidenceCitation:
    candidate = evidence.candidate
    local_start = candidate.sanitized_text.find(excerpt)
    if local_start < 0:
        raise CitationValidationError("citation excerpt is not present in the retrieved chunk")
    start = candidate.normalized_start + local_start
    end = start + len(excerpt)
    return EvidenceCitation(
        candidate.source_relative_path,
        candidate.source_sha256,
        candidate.chunk_id,
        candidate.chunk_sha256,
        candidate.heading_hierarchy,
        start,
        end,
        candidate.processing_version,
        candidate.authorization_reference,
        candidate.corpus_version,
        excerpt,
    )


@dataclass(frozen=True)
class CitationValidationReport:
    valid: bool
    validated_count: int


def validate_citations(
    question: str,
    answer: str,
    citations: Sequence[EvidenceCitation],
    evidence: Sequence[RankedEvidence],
    filters: RetrievalFilters,
    profile_key: str,
    config: SufficiencyConfig,
) -> CitationValidationReport:
    if not citations:
        raise CitationValidationError("an answered response requires at least one citation")
    if answer != " ".join(citation.excerpt for citation in citations):
        raise CitationValidationError("extractive answers may contain only the ordered cited excerpts")
    indexed: Mapping[str, RankedEvidence] = {item.candidate.chunk_id: item for item in evidence}
    question_tokens = content_tokens(question)
    for citation in citations:
        ranked = indexed.get(citation.chunk_id)
        if ranked is None:
            raise CitationValidationError("cited chunk was not present in authorized retrieval results")
        candidate = ranked.candidate
        expected = (
            candidate.source_relative_path,
            candidate.source_sha256,
            candidate.chunk_sha256,
            candidate.heading_hierarchy,
            candidate.processing_version,
            candidate.authorization_reference,
            candidate.corpus_version,
        )
        actual = (
            citation.source_relative_path,
            citation.source_sha256,
            citation.chunk_sha256,
            citation.heading_hierarchy,
            citation.processing_version,
            citation.authorization_reference,
            citation.corpus_version,
        )
        if actual != expected:
            raise CitationValidationError("citation provenance does not match the retrieved chunk")
        if candidate.retrieval_corpus_id != filters.corpus_id or candidate.retrieval_access_policy != filters.access_policy:
            raise CitationValidationError("citation is outside the authorized retrieval scope")
        if candidate.authorization_reference != filters.authorization_reference or candidate.profile_key != profile_key:
            raise CitationValidationError("citation authorization or model profile does not match")
        if not (candidate.normalized_start <= citation.normalized_start < citation.normalized_end <= candidate.normalized_end):
            raise CitationValidationError("citation span is outside the normalized sanitized chunk")
        local_start = citation.normalized_start - candidate.normalized_start
        local_end = citation.normalized_end - candidate.normalized_start
        if candidate.sanitized_text[local_start:local_end] != citation.excerpt:
            raise CitationValidationError("citation excerpt does not match its normalized sanitized span")
        if citation.excerpt not in answer:
            raise CitationValidationError("the cited excerpt does not directly support any extractive answer text")
        overlap = len(question_tokens & content_tokens(citation.excerpt + " " + " ".join(citation.heading_hierarchy)))
        similarity = candidate.cosine_similarity or -1.0
        if overlap < config.min_lexical_overlap and similarity < config.strong_semantic_similarity:
            raise CitationValidationError("citation does not meet claim-relevance requirements")
    return CitationValidationReport(True, len(citations))
