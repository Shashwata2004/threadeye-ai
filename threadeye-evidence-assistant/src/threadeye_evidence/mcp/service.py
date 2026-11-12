"""Bounded read-only façade over the existing retrieval and answer engines."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.answering.policy import normalize_question_input, rejected_request_reason
from threadeye_evidence.mcp.authorization import AuthorizationConfigurationError, TrustedAuthorizationContext
from threadeye_evidence.mcp.database import ReadOnlyEvidenceDatabase
from threadeye_evidence.retrieval.engine import HybridRetriever
from threadeye_evidence.retrieval.models import RetrievalMode
from threadeye_evidence.retrieval.store import RetrievalStore
from threadeye_evidence.vector.embeddings import FastEmbedProvider


class MCPRequestError(ValueError):
    """A safe client-visible validation or policy error."""


class EvidenceMCPService:
    def __init__(
        self,
        authorization: TrustedAuthorizationContext,
        retriever: HybridRetriever,
    ) -> None:
        authorization.validate_embedding_profile(retriever.provider.metadata)
        self.authorization = authorization
        self.retriever = retriever
        self.answer_engine = EvidenceAnswerEngine(retriever)

    def _validate_text(self, value: str, *, field: str) -> str:
        try:
            normalized = normalize_question_input(value).strip()
        except (TypeError, ValueError, UnicodeError) as exc:
            raise MCPRequestError(f"{field} is malformed") from exc
        if not normalized:
            raise MCPRequestError(f"{field} must not be empty")
        if len(normalized) > self.authorization.max_query_chars:
            raise MCPRequestError(f"{field} exceeds the configured length limit")
        return normalized

    def _validate_mode(self, mode: str) -> str:
        try:
            return RetrievalMode(mode).value
        except (TypeError, ValueError) as exc:
            raise MCPRequestError("mode must be keyword, vector, or hybrid") from exc

    def _validate_top_k(self, top_k: int) -> int:
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= self.authorization.max_top_k:
            raise MCPRequestError(f"top_k must be from 1 through {self.authorization.max_top_k}")
        return top_k

    def _bounded(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        if len(encoded) > self.authorization.max_response_bytes:
            raise MCPRequestError("response exceeds the configured size limit")
        return payload

    def search(self, query: str, mode: str, top_k: int) -> dict[str, Any]:
        value = self._validate_text(query, field="query")
        active_mode = self._validate_mode(mode)
        limit = self._validate_top_k(top_k)
        rejected = rejected_request_reason(value)
        if rejected:
            raise MCPRequestError(f"query rejected by evidence security policy: {rejected}")
        response = self.retriever.search(
            value,
            mode=active_mode,
            filters=self.authorization.filters(),
            top_k=limit,
            candidate_k=max(limit, min(20, limit * 4)),
        )
        results = []
        for ranked in response.results:
            candidate = ranked.candidate
            if candidate.source_relative_path != self.authorization.allowed_source:
                raise MCPRequestError("retrieval returned evidence outside the trusted source scope")
            results.append({
                "source_title": candidate.heading_hierarchy[0] if candidate.heading_hierarchy else candidate.source_relative_path,
                "source_relative_path": candidate.source_relative_path,
                "source_sha256": candidate.source_sha256,
                "chunk_id": candidate.chunk_id,
                "chunk_sha256": candidate.chunk_sha256,
                "heading_hierarchy": list(candidate.heading_hierarchy),
                "sanitized_text": candidate.sanitized_text,
                "normalized_start": candidate.normalized_start,
                "normalized_end": candidate.normalized_end,
                "processing_version": candidate.processing_version,
                "corpus_version": candidate.corpus_version,
                "retrieval_methods": list(ranked.retrieval_methods),
                "keyword_rank": ranked.keyword_rank,
                "vector_rank": ranked.vector_rank,
                "keyword_score": candidate.keyword_score,
                "cosine_similarity": candidate.cosine_similarity,
                "rrf_score": ranked.rrf_score,
            })
        return self._bounded({
            "status": "ok",
            "query": value,
            "mode": response.mode,
            "result_count": len(results),
            "backend_status": dict(response.backend_status),
            "results": results,
        })

    def answer(self, question: str, mode: str) -> dict[str, Any]:
        value = self._validate_text(question, field="question")
        active_mode = self._validate_mode(mode)
        response = self.answer_engine.answer(
            value,
            filters=self.authorization.filters(),
            mode=active_mode,
            top_k=self.authorization.max_top_k,
            candidate_k=min(20, self.authorization.max_top_k * 4),
        )
        payload = response.to_mapping()
        if any(citation["source_relative_path"] != self.authorization.allowed_source for citation in payload["citations"]):
            raise MCPRequestError("answer citation is outside the trusted source scope")
        return self._bounded(payload)

    def list_sources(self) -> dict[str, Any]:
        rows = self.retriever.store.list_sources(self.authorization.filters(), self.retriever.provider.metadata)
        sources = [{
            **row,
            "description": self.authorization.source_description,
        } for row in rows if row["source_relative_path"] == self.authorization.allowed_source]
        return self._bounded({
            "corpus_id": self.authorization.corpus_id,
            "source_count": len(sources),
            "sources": sources,
        })

    def capabilities(self) -> dict[str, Any]:
        return self._bounded({
            "server": "ThreadEye Evidence MCP Server",
            "transport": "launcher-selected stdio or authenticated local streamable-http",
            "transports": ["stdio", "streamable-http"],
            "read_only": True,
            "retrieval_modes": [mode.value for mode in RetrievalMode],
            "answer_mode": "extractive",
            "embedding": self.retriever.provider.metadata.to_mapping(),
            "citation_validation": True,
            "safe_abstention": True,
            "scope": "authorized fictional synthetic evidence only",
            "detector_distinction": "Evidence examples describe fictional/simulated ThreadEye workflows; MCP does not run the detector.",
            "limitations": [
                "No LLM generation, operational verdict, scoring change, filesystem tool, SQL tool, or shell tool.",
                "No production ThreadEye, Supabase, buyer, inspection-image, report, or user access.",
                "stdio is local transport, not cryptographic caller authentication; HTTP requires a validated token.",
            ],
            "authorization": self.authorization.public_mapping(),
        })

    def security_policy(self) -> dict[str, Any]:
        return self._bounded({
            "read_only": True,
            "trusted_startup_context_required": True,
            "client_scope_arguments_allowed": False,
            "allowed_source": self.authorization.allowed_source,
            "forbidden_operations": [
                "filesystem read/write", "shell execution", "generic SQL", "HTTP requests",
                "indexing", "inspection updates", "verdict approval", "audit modification",
            ],
            "limits": self.authorization.public_mapping()["limits"],
        })


def service_from_environment() -> EvidenceMCPService:
    authorization = TrustedAuthorizationContext.from_environment()
    dsn = os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL")
    if not dsn:
        raise AuthorizationConfigurationError("read-only MCP database context is missing")
    cache = Path(os.environ.get("THREADEYE_EVIDENCE_MODEL_CACHE", "build/model-cache"))
    provider = FastEmbedProvider(cache, local_files_only=True)
    database = ReadOnlyEvidenceDatabase.from_dsn(dsn)
    return EvidenceMCPService(authorization, HybridRetriever(RetrievalStore(database), provider))
