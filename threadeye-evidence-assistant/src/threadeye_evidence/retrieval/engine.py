"""Three-mode retrieval engine with strict failure reporting and RRF fusion."""

from __future__ import annotations

from time import perf_counter

from threadeye_evidence.retrieval.fusion import RRFConfig, fuse_rrf, rank_single
from threadeye_evidence.retrieval.models import (
    RetrievalFilters,
    RetrievalMode,
    RetrievalResponse,
    RetrievalValidationError,
    validate_limit,
    validate_query,
)
from threadeye_evidence.retrieval.store import RetrievalStore
from threadeye_evidence.vector.embeddings import EmbeddingProvider


class RetrievalBackendError(RuntimeError):
    """A requested retrieval branch failed; hybrid success is never fabricated."""


class HybridRetriever:
    def __init__(self, store: RetrievalStore, provider: EmbeddingProvider) -> None:
        self.store = store
        self.provider = provider

    def search(
        self,
        query: str,
        *,
        mode: RetrievalMode | str,
        filters: RetrievalFilters,
        top_k: int = 5,
        candidate_k: int = 20,
        rrf_config: RRFConfig | None = None,
    ) -> RetrievalResponse:
        value = validate_query(query)
        final_limit = validate_limit(top_k)
        candidate_limit = validate_limit(candidate_k, field_name="candidate_k")
        if candidate_limit < final_limit:
            raise RetrievalValidationError("candidate_k must be greater than or equal to top_k")
        try:
            active_mode = mode if isinstance(mode, RetrievalMode) else RetrievalMode(mode)
        except ValueError as exc:
            raise RetrievalValidationError("mode must be keyword, vector, or hybrid") from exc
        config = rrf_config or RRFConfig()
        backend_status: dict[str, str] = {}
        started = perf_counter()

        keyword_results = []
        vector_results = []
        if active_mode in {RetrievalMode.KEYWORD, RetrievalMode.HYBRID}:
            try:
                keyword_results = self.store.keyword_search(
                    value,
                    self.provider.metadata,
                    filters,
                    top_k=candidate_limit,
                )
            except Exception as exc:
                raise RetrievalBackendError("keyword retrieval failed") from exc
            backend_status["keyword"] = "ok" if keyword_results else "no_matches"

        if active_mode in {RetrievalMode.VECTOR, RetrievalMode.HYBRID}:
            try:
                query_vector = self.provider.embed_query(value)
                vector_results = self.store.vector_search(
                    query_vector,
                    self.provider.metadata,
                    filters,
                    top_k=candidate_limit,
                )
            except Exception as exc:
                raise RetrievalBackendError("vector retrieval failed") from exc
            backend_status["vector"] = "ok" if vector_results else "no_matches"

        if active_mode is RetrievalMode.HYBRID:
            ranked = fuse_rrf(
                keyword_results,
                vector_results,
                top_k=final_limit,
                config=config,
            )
            rrf_mapping = config.to_mapping()
        elif active_mode is RetrievalMode.KEYWORD:
            ranked = rank_single(keyword_results, mode="keyword", top_k=final_limit)
            rrf_mapping = None
        else:
            ranked = rank_single(vector_results, mode="vector", top_k=final_limit)
            rrf_mapping = None

        latency_ms = (perf_counter() - started) * 1_000.0
        return RetrievalResponse(
            value,
            active_mode.value,
            final_limit,
            candidate_limit,
            filters,
            backend_status,
            latency_ms,
            tuple(ranked),
            rrf_mapping,
        )
