"""Versioned, conservative multi-signal evidence-sufficiency assessment."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Sequence

from threadeye_evidence.answering.models import AbstentionReason, SufficiencyDecision
from threadeye_evidence.answering.policy import contains_explicit_contradiction, contains_untrusted_instruction
from threadeye_evidence.retrieval.models import RankedEvidence


_TOKEN = re.compile(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*")
_IDENTIFIER = re.compile(r"\b[A-Z]{2,}(?:-[A-Z0-9]+)+\b")
_STOPWORDS = frozenset(
    "a an and are as at be before by can did do does for from how i in is it of on or that the this to was what when where which who why with".split()
)


def content_tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN.findall(text) if token.lower() not in _STOPWORDS and len(token) > 1}


@dataclass(frozen=True)
class SufficiencyConfig:
    version: str = "prompt06-dev-v1"
    min_question_tokens: int = 2
    min_semantic_similarity: float = 0.62
    strong_semantic_similarity: float = 0.70
    min_semantic_margin: float = 0.015
    min_lexical_overlap: int = 1
    max_supporting_chunks: int = 2

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("sufficiency configuration requires a version")
        if not 1 <= self.min_question_tokens <= 10:
            raise ValueError("min_question_tokens must be from 1 through 10")
        if not 0.55 <= self.min_semantic_similarity <= 0.90:
            raise ValueError("min_semantic_similarity must be from 0.55 through 0.90")
        if not self.min_semantic_similarity <= self.strong_semantic_similarity <= 0.95:
            raise ValueError("strong semantic similarity must be at least the minimum and at most 0.95")
        if not 0.0 <= self.min_semantic_margin <= 0.25:
            raise ValueError("min_semantic_margin must be from 0 through 0.25")
        if not 1 <= self.min_lexical_overlap <= 10:
            raise ValueError("min_lexical_overlap must be from 1 through 10")
        if not 1 <= self.max_supporting_chunks <= 3:
            raise ValueError("max_supporting_chunks must be from 1 through 3")

    def to_mapping(self) -> dict[str, object]:
        return asdict(self)


def assess_sufficiency(
    question: str,
    results: Sequence[RankedEvidence],
    config: SufficiencyConfig,
) -> SufficiencyDecision:
    query_tokens = content_tokens(question)
    identifiers = set(_IDENTIFIER.findall(question))
    if len(query_tokens) < config.min_question_tokens and not identifiers:
        return SufficiencyDecision(False, AbstentionReason.AMBIGUOUS_QUESTION.value, (), {"query_token_count": len(query_tokens), "config_version": config.version})
    if not results:
        return SufficiencyDecision(False, AbstentionReason.NO_EVIDENCE.value, (), {"config_version": config.version})
    if any(contains_explicit_contradiction(item.candidate.sanitized_text) for item in results):
        return SufficiencyDecision(False, AbstentionReason.CONTRADICTORY_EVIDENCE.value, (), {"config_version": config.version})

    safe_results = [item for item in results if not contains_untrusted_instruction(item.candidate.sanitized_text)]
    if not safe_results:
        return SufficiencyDecision(False, AbstentionReason.UNTRUSTED_INSTRUCTION_EVIDENCE.value, (), {"config_version": config.version})
    def selection_score(item: RankedEvidence) -> tuple[float, str]:
        candidate_tokens = content_tokens(item.candidate.sanitized_text + " " + " ".join(item.candidate.heading_hierarchy))
        candidate_overlap = len(query_tokens & candidate_tokens)
        candidate_identifiers = set(_IDENTIFIER.findall(item.candidate.sanitized_text))
        identifier_bonus = 100.0 if identifiers & candidate_identifiers else 0.0
        keyword_bonus = 20.0 if item.keyword_rank is not None and (item.candidate.keyword_score or 0) > 0 else 0.0
        semantic = item.candidate.cosine_similarity or 0.0
        return (identifier_bonus + keyword_bonus + candidate_overlap * 5.0 + semantic, item.candidate.chunk_id)

    selected = max(safe_results, key=selection_score)
    candidate = selected.candidate
    evidence_tokens = content_tokens(candidate.sanitized_text + " " + " ".join(candidate.heading_hierarchy))
    overlap = len(query_tokens & evidence_tokens)
    similarity = candidate.cosine_similarity
    exact_identifier = bool(identifiers & set(_IDENTIFIER.findall(candidate.sanitized_text)))
    keyword_match = selected.keyword_rank is not None and candidate.keyword_score is not None and candidate.keyword_score > 0
    other_similarities = [item.candidate.cosine_similarity for item in safe_results if item is not selected and item.candidate.cosine_similarity is not None]
    second_similarity = max(other_similarities) if other_similarities else None
    margin = similarity - second_similarity if similarity is not None and second_similarity is not None else None

    semantic_supported = similarity is not None and similarity >= config.min_semantic_similarity and (
        overlap >= config.min_lexical_overlap
        or similarity >= config.strong_semantic_similarity
    )
    unambiguous = keyword_match or exact_identifier or overlap >= 2 or margin is None or margin >= config.min_semantic_margin
    sufficient = (exact_identifier or keyword_match or semantic_supported) and unambiguous
    signals = {
        "config_version": config.version,
        "query_token_count": len(query_tokens),
        "lexical_overlap": overlap,
        "exact_identifier": exact_identifier,
        "keyword_match": keyword_match,
        "cosine_similarity": similarity,
        "semantic_margin": margin,
        "semantic_supported": semantic_supported,
        "unambiguous": unambiguous,
        "selected_original_rank": selected.final_rank,
    }
    if not sufficient:
        return SufficiencyDecision(False, AbstentionReason.INSUFFICIENT_RELEVANCE.value, (), signals)
    return SufficiencyDecision(True, None, (candidate.chunk_id,), signals)
