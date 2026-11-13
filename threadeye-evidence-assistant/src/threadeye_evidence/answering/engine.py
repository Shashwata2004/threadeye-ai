"""Authorized retrieval-to-answer orchestration with safe abstention."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from threadeye_evidence.answering.abstention import SufficiencyConfig, assess_sufficiency
from threadeye_evidence.answering.citations import citation_from_excerpt, validate_citations
from threadeye_evidence.answering.extractive import ExtractiveAnswerProvider
from threadeye_evidence.answering.models import (
    AbstentionReason,
    AnswerStatus,
    EvidenceAnswer,
    SufficiencyDecision,
)
from threadeye_evidence.answering.policy import QuestionSecurityError, normalize_question_input, rejected_request_reason
from threadeye_evidence.corpus.sanitization import SanitizationRejected, sanitize_markdown
from threadeye_evidence.retrieval.engine import HybridRetriever, RetrievalBackendError
from threadeye_evidence.retrieval.fusion import RRFConfig
from threadeye_evidence.retrieval.models import MAX_QUERY_CHARS, RetrievalFilters, RetrievalMode, validate_limit, validate_query


_LIMITATIONS = (
    "This is deterministic extraction from authorized fictional evidence, not LLM generation.",
    "It cannot approve rolls, alter scoring, access production records, or replace human review.",
    "Citation offsets refer to sanitized normalized text, not original raw document bytes.",
)


class EvidenceAnswerEngine:
    def __init__(
        self,
        retriever: HybridRetriever,
        *,
        sufficiency_config: SufficiencyConfig | None = None,
        provider: ExtractiveAnswerProvider | None = None,
    ) -> None:
        self.retriever = retriever
        self.sufficiency_config = sufficiency_config or SufficiencyConfig()
        self.provider = provider or ExtractiveAnswerProvider()

    def _response(
        self,
        question: str,
        filters: RetrievalFilters,
        mode: str,
        started: float,
        *,
        status: AnswerStatus,
        reason: str | None,
        retrieval_metadata: dict[str, Any] | None = None,
        sufficiency: SufficiencyDecision | None = None,
        answer: str | None = None,
        citations: tuple = (),
        supporting_chunk_ids: tuple[str, ...] = (),
        processing_versions: tuple[str, ...] = (),
    ) -> EvidenceAnswer:
        return EvidenceAnswer(
            question=question,
            status=status.value,
            answer_mode=self.provider.answer_mode,
            answer=answer,
            citations=citations,
            supporting_chunk_ids=supporting_chunk_ids,
            retrieval_mode=mode,
            retrieval_metadata=retrieval_metadata or {},
            abstention_reason=reason,
            limitations=_LIMITATIONS,
            corpus_id=filters.corpus_id,
            model_profile=self.retriever.provider.metadata.to_mapping(),
            processing_versions=processing_versions,
            sufficiency=sufficiency,
            latency_ms=(perf_counter() - started) * 1_000.0,
        )

    def answer(
        self,
        question: str,
        *,
        filters: RetrievalFilters,
        mode: RetrievalMode | str = RetrievalMode.HYBRID,
        top_k: int = 5,
        candidate_k: int = 20,
        rrf_config: RRFConfig | None = None,
    ) -> EvidenceAnswer:
        started = perf_counter()
        safe_question = ""
        if isinstance(question, str):
            try:
                safe_question = sanitize_markdown(question[:1_000]).text
            except SanitizationRejected:
                safe_question = "[REDACTED_UNSAFE_INPUT]"
        active_mode = mode.value if isinstance(mode, RetrievalMode) else str(mode)
        try:
            normalized = normalize_question_input(question)
            if len(normalized.strip()) > MAX_QUERY_CHARS:
                return self._response(
                    safe_question.strip(), filters, active_mode, started,
                    status=AnswerStatus.VALIDATION_ERROR,
                    reason=AbstentionReason.RESOURCE_LIMIT_EXCEEDED.value,
                    retrieval_metadata={"failure_stage": "query_length", "degraded": False},
                )
            value = validate_query(normalized)
        except (QuestionSecurityError, ValueError, UnicodeError):
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.VALIDATION_ERROR,
                reason=AbstentionReason.MALFORMED_INPUT.value,
                retrieval_metadata={"failure_stage": "input_validation", "degraded": False},
            )
        try:
            validate_limit(top_k)
            validate_limit(candidate_k, field_name="candidate_k")
            if candidate_k < top_k:
                raise ValueError("candidate_k must not be smaller than top_k")
        except ValueError:
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.VALIDATION_ERROR,
                reason=AbstentionReason.RESOURCE_LIMIT_EXCEEDED.value,
                retrieval_metadata={"failure_stage": "resource_validation", "degraded": False},
            )
        try:
            RetrievalMode(active_mode)
        except ValueError:
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.VALIDATION_ERROR,
                reason=AbstentionReason.INVALID_RETRIEVAL_MODE.value,
                retrieval_metadata={"failure_stage": "mode_validation", "degraded": False},
            )
        rejected = rejected_request_reason(value)
        if rejected:
            status = AnswerStatus.INSUFFICIENT_EVIDENCE if rejected == AbstentionReason.CONTRADICTORY_EVIDENCE.value else AnswerStatus.UNSUPPORTED_REQUEST
            decision = SufficiencyDecision(False, rejected, (), {"policy_preflight": True, "config_version": self.sufficiency_config.version})
            return self._response(safe_question.strip(), filters, active_mode, started, status=status, reason=rejected, sufficiency=decision)

        try:
            authorized_count = self.retriever.store.authorization_scope_count(filters, self.retriever.provider.metadata)
        except Exception:
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.RETRIEVAL_ERROR,
                reason=AbstentionReason.RETRIEVAL_BACKEND_FAILURE.value,
                retrieval_metadata={"failure_stage": "authorization_database", "degraded": False},
            )
        if authorized_count == 0:
            decision = SufficiencyDecision(False, AbstentionReason.AUTHORIZATION_SCOPE_EMPTY.value, (), {"authorized_chunk_count": 0})
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.UNAUTHORIZED,
                reason=AbstentionReason.AUTHORIZATION_SCOPE_EMPTY.value,
                sufficiency=decision,
            )

        try:
            retrieved = self.retriever.search(
                value,
                mode=mode,
                filters=filters,
                top_k=top_k,
                candidate_k=candidate_k,
                rrf_config=rrf_config,
            )
        except RetrievalBackendError as exc:
            message = str(exc).lower()
            stage = "keyword_retrieval" if "keyword" in message else "vector_retrieval" if "vector" in message else "hybrid_retrieval"
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.RETRIEVAL_ERROR,
                reason=AbstentionReason.RETRIEVAL_BACKEND_FAILURE.value,
                retrieval_metadata={"failure_stage": stage, "degraded": False},
            )
        except Exception:
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.RETRIEVAL_ERROR,
                reason=AbstentionReason.RETRIEVAL_BACKEND_FAILURE.value,
                retrieval_metadata={"failure_stage": "retrieval", "degraded": False},
            )
        metadata = {
            "backend_status": dict(retrieved.backend_status),
            "retrieval_latency_ms": retrieved.latency_ms,
            "retrieved_count": len(retrieved.results),
            "retrieved_chunk_ids": [item.candidate.chunk_id for item in retrieved.results],
            "sufficiency_config": self.sufficiency_config.to_mapping(),
        }
        decision = assess_sufficiency(value, retrieved.results, self.sufficiency_config)
        if not decision.sufficient:
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                reason=decision.reason,
                retrieval_metadata=metadata,
                sufficiency=decision,
            )

        selected = tuple(item for item in retrieved.results if item.candidate.chunk_id in decision.supporting_chunk_ids)
        try:
            extracted = self.provider.build(value, selected)
            citations = tuple(citation_from_excerpt(item.ranked_evidence, item.excerpt) for item in extracted.supports)
            validate_citations(
                value,
                extracted.answer,
                citations,
                selected,
                filters,
                self.retriever.provider.metadata.profile_key,
                self.sufficiency_config,
            )
            metadata["citation_validation"] = {"valid": True, "validated_count": len(citations)}
        except Exception:
            metadata["failure_stage"] = "citation_validation"
            metadata["degraded"] = False
            failed = SufficiencyDecision(False, AbstentionReason.INVALID_CITATION.value, (), decision.signals)
            return self._response(
                safe_question.strip(), filters, active_mode, started,
                status=AnswerStatus.CITATION_VALIDATION_FAILED,
                reason=AbstentionReason.INVALID_CITATION.value,
                retrieval_metadata=metadata,
                sufficiency=failed,
            )
        processing = tuple(sorted({item.ranked_evidence.candidate.processing_version for item in extracted.supports}))
        return self._response(
            safe_question.strip(), filters, active_mode, started,
            status=AnswerStatus.ANSWERED,
            reason=None,
            retrieval_metadata=metadata,
            sufficiency=decision,
            answer=extracted.answer,
            citations=citations,
            supporting_chunk_ids=decision.supporting_chunk_ids,
            processing_versions=processing,
        )
