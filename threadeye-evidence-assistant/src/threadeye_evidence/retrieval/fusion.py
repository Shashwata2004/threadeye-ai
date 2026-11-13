"""Deterministic weighted reciprocal-rank fusion."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, replace
from typing import Sequence

from threadeye_evidence.retrieval.models import (
    EvidenceCandidate,
    RankedEvidence,
    RetrievalValidationError,
    validate_limit,
)


@dataclass(frozen=True)
class RRFConfig:
    k: float = 60.0
    keyword_weight: float = 1.0
    vector_weight: float = 1.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.k) or not 1.0 <= self.k <= 1_000.0:
            raise RetrievalValidationError("RRF k must be finite and from 1 through 1000")
        for name in ("keyword_weight", "vector_weight"):
            value = getattr(self, name)
            if not math.isfinite(value) or not 0.0 < value <= 10.0:
                raise RetrievalValidationError(f"{name} must be finite, positive, and at most 10")

    def to_mapping(self) -> dict[str, float]:
        return asdict(self)


def _merge_candidates(left: EvidenceCandidate, right: EvidenceCandidate) -> EvidenceCandidate:
    if left.identity_signature != right.identity_signature:
        raise RetrievalValidationError("retrieval branches returned conflicting provenance for one chunk")
    return replace(
        left,
        keyword_score=left.keyword_score if left.keyword_score is not None else right.keyword_score,
        cosine_distance=left.cosine_distance if left.cosine_distance is not None else right.cosine_distance,
        cosine_similarity=left.cosine_similarity if left.cosine_similarity is not None else right.cosine_similarity,
    )


def fuse_rrf(
    keyword_results: Sequence[EvidenceCandidate],
    vector_results: Sequence[EvidenceCandidate],
    *,
    top_k: int,
    config: RRFConfig,
) -> list[RankedEvidence]:
    validate_limit(top_k)
    keyword_ranks = {item.chunk_id: rank for rank, item in enumerate(keyword_results, start=1)}
    vector_ranks = {item.chunk_id: rank for rank, item in enumerate(vector_results, start=1)}
    candidates: dict[str, EvidenceCandidate] = {}
    for item in (*keyword_results, *vector_results):
        existing = candidates.get(item.chunk_id)
        candidates[item.chunk_id] = item if existing is None else _merge_candidates(existing, item)

    scored: list[tuple[float, str, EvidenceCandidate]] = []
    for chunk_id, candidate in candidates.items():
        score = 0.0
        if chunk_id in keyword_ranks:
            score += config.keyword_weight / (config.k + keyword_ranks[chunk_id])
        if chunk_id in vector_ranks:
            score += config.vector_weight / (config.k + vector_ranks[chunk_id])
        scored.append((score, chunk_id, candidate))
    scored.sort(key=lambda item: (-item[0], item[1]))

    results: list[RankedEvidence] = []
    for final_rank, (score, chunk_id, candidate) in enumerate(scored[:top_k], start=1):
        methods = tuple(
            method
            for method, ranks in (("keyword", keyword_ranks), ("vector", vector_ranks))
            if chunk_id in ranks
        )
        results.append(
            RankedEvidence(
                candidate,
                final_rank,
                methods,
                keyword_ranks.get(chunk_id),
                vector_ranks.get(chunk_id),
                score,
            )
        )
    return results


def rank_single(results: Sequence[EvidenceCandidate], *, mode: str, top_k: int) -> list[RankedEvidence]:
    validate_limit(top_k)
    return [
        RankedEvidence(
            candidate,
            rank,
            (mode,),
            rank if mode == "keyword" else None,
            rank if mode == "vector" else None,
            None,
        )
        for rank, candidate in enumerate(results[:top_k], start=1)
    ]
