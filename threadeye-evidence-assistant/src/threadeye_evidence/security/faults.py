"""Controlled companion-only fault injection; never disrupts a live service."""

from __future__ import annotations

from dataclasses import replace
from enum import Enum

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.retrieval.engine import HybridRetriever
from threadeye_evidence.retrieval.models import RetrievalResponse


class FaultScenario(str, Enum):
    DATABASE_UNAVAILABLE = "database_unavailable"
    DATABASE_TIMEOUT = "database_timeout"
    EMBEDDING_UNAVAILABLE = "embedding_unavailable"
    KEYWORD_UNAVAILABLE = "keyword_unavailable"
    VECTOR_UNAVAILABLE = "vector_unavailable"
    INCOMPATIBLE_PROFILE = "incompatible_profile"
    CITATION_TAMPER = "citation_tamper"
    SERVICE_STOPPED = "service_stopped"


class _StoreFault:
    def __init__(self, delegate, scenario: FaultScenario) -> None:
        self.delegate = delegate
        self.scenario = scenario

    def authorization_scope_count(self, filters, metadata):
        if self.scenario in {FaultScenario.DATABASE_UNAVAILABLE, FaultScenario.SERVICE_STOPPED}:
            raise ConnectionError("simulated isolated companion database unavailable")
        if self.scenario is FaultScenario.DATABASE_TIMEOUT:
            raise TimeoutError("simulated bounded database timeout")
        return self.delegate.authorization_scope_count(filters, metadata)

    def keyword_search(self, *args, **kwargs):
        if self.scenario is FaultScenario.KEYWORD_UNAVAILABLE:
            raise RuntimeError("simulated keyword backend failure")
        return self.delegate.keyword_search(*args, **kwargs)

    def vector_search(self, *args, **kwargs):
        if self.scenario in {FaultScenario.VECTOR_UNAVAILABLE, FaultScenario.INCOMPATIBLE_PROFILE}:
            raise RuntimeError(f"simulated {self.scenario.value}")
        return self.delegate.vector_search(*args, **kwargs)

    def environment_info(self):
        return self.delegate.environment_info()


class _ProviderFault:
    def __init__(self, delegate, scenario: FaultScenario) -> None:
        self.delegate = delegate
        self.scenario = scenario
        self.metadata = delegate.metadata

    def embed_query(self, value):
        if self.scenario is FaultScenario.EMBEDDING_UNAVAILABLE:
            raise RuntimeError("simulated embedding model unavailable")
        return self.delegate.embed_query(value)


class _CitationTamperRetriever:
    def __init__(self, delegate) -> None:
        self.delegate = delegate
        self.store = delegate.store
        self.provider = delegate.provider

    def search(self, *args, **kwargs):
        response = self.delegate.search(*args, **kwargs)
        if not response.results:
            return response
        forged = tuple(
            replace(item, candidate=replace(item.candidate, chunk_sha256="f" * 64))
            for item in response.results
        )
        return RetrievalResponse(
            response.query, response.mode, response.top_k, response.candidate_k,
            response.filters, response.backend_status, response.latency_ms,
            forged, response.rrf_config,
        )


def fault_engine(engine: EvidenceAnswerEngine, scenario: FaultScenario | str) -> EvidenceAnswerEngine:
    """Return an isolated wrapper that injects one declared failure without mutating dependencies."""

    active = FaultScenario(scenario)
    if active is FaultScenario.CITATION_TAMPER:
        retriever = _CitationTamperRetriever(engine.retriever)
    else:
        store = _StoreFault(engine.retriever.store, active)
        provider = _ProviderFault(engine.retriever.provider, active)
        retriever = HybridRetriever(store, provider)
    return EvidenceAnswerEngine(retriever, sufficiency_config=engine.sufficiency_config, provider=engine.provider)
