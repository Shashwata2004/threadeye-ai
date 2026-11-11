"""Independent answerability, abstention, citation, and structure evaluation."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.answering.models import AnswerStatus, EvidenceAnswer
from threadeye_evidence.retrieval.models import RetrievalFilters, RetrievalValidationError


@dataclass(frozen=True)
class AnswerEvaluationCase:
    case_id: str
    split: str
    question: str
    answerable: bool
    expected_status: str
    expected_sections: tuple[str, ...]
    expected_reason: str | None
    category: str
    notes: str
    filter_override: dict[str, str]


@dataclass(frozen=True)
class AnswerEvaluationDataset:
    dataset_version: str
    corpus_id: str
    access_policy: str
    authorization_reference: str
    cases: tuple[AnswerEvaluationCase, ...]


def load_answer_evaluation_dataset(path: Path) -> AnswerEvaluationDataset:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("labels_created_before_prediction_review") is not True:
        raise RetrievalValidationError("answer evaluation labels must predate prediction review")
    rows = raw.get("cases")
    if not isinstance(rows, list) or len(rows) < 40:
        raise RetrievalValidationError("answer evaluation requires at least 40 cases")
    cases: list[AnswerEvaluationCase] = []
    identifiers: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            raise RetrievalValidationError("answer evaluation cases must be objects")
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in identifiers:
            raise RetrievalValidationError("answer evaluation case IDs must be unique")
        identifiers.add(case_id)
        split = row.get("split")
        if split not in {"development", "held_out"}:
            raise RetrievalValidationError("answer evaluation split must be development or held_out")
        answerable = row.get("answerable")
        if not isinstance(answerable, bool):
            raise RetrievalValidationError("answerable must be boolean")
        expected_status = row.get("expected_status")
        valid_statuses = {status.value for status in AnswerStatus}
        if expected_status not in valid_statuses or answerable != (expected_status == AnswerStatus.ANSWERED.value):
            raise RetrievalValidationError("expected status and answerability disagree")
        expected_sections = row.get("expected_sections")
        if not isinstance(expected_sections, list) or any(not isinstance(item, str) or not item for item in expected_sections):
            raise RetrievalValidationError("expected_sections must be non-empty strings")
        if answerable != bool(expected_sections):
            raise RetrievalValidationError("answerable cases require sections; abstentions must not have sections")
        expected_reason = row.get("expected_reason")
        if answerable and expected_reason is not None:
            raise RetrievalValidationError("answerable cases cannot have abstention reasons")
        if not answerable and (not isinstance(expected_reason, str) or not expected_reason):
            raise RetrievalValidationError("unsupported cases require an abstention reason")
        for name in ("question", "category", "notes"):
            if not isinstance(row.get(name), str) or not row[name].strip():
                raise RetrievalValidationError(f"answer evaluation {name} is invalid")
        override = row.get("filter_override", {})
        if not isinstance(override, dict) or any(key not in {"access_policy", "authorization_reference", "source_relative_path"} for key in override):
            raise RetrievalValidationError("filter_override contains an unsupported field")
        if any(not isinstance(value, str) or not value for value in override.values()):
            raise RetrievalValidationError("filter overrides must be non-empty strings")
        cases.append(
            AnswerEvaluationCase(
                case_id, split, row["question"], answerable, expected_status, tuple(expected_sections),
                expected_reason, row["category"], row["notes"], dict(override),
            )
        )
    positives = sum(case.answerable for case in cases)
    negatives = len(cases) - positives
    if positives < 20 or negatives < 20:
        raise RetrievalValidationError("answer evaluation requires at least 20 positive and 20 negative cases")
    for split in ("development", "held_out"):
        subset = [case for case in cases if case.split == split]
        if not subset or not any(case.answerable for case in subset) or not any(not case.answerable for case in subset):
            raise RetrievalValidationError("each split requires positive and negative cases")
    required = ("dataset_version", "corpus_id", "access_policy", "authorization_reference")
    if any(not isinstance(raw.get(name), str) or not raw[name].strip() for name in required):
        raise RetrievalValidationError("answer evaluation dataset metadata is invalid")
    return AnswerEvaluationDataset(raw["dataset_version"], raw["corpus_id"], raw["access_policy"], raw["authorization_reference"], tuple(cases))


def _structured_valid(response: EvidenceAnswer) -> bool:
    if response.status == AnswerStatus.ANSWERED.value:
        return bool(response.answer and response.citations and response.supporting_chunk_ids and response.abstention_reason is None)
    return response.answer is None and not response.citations and bool(response.abstention_reason)


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [record for record in records if record["answerable"]]
    negatives = [record for record in records if not record["answerable"]]
    true_answers = sum(record["predicted_answered"] for record in positives)
    false_abstentions = len(positives) - true_answers
    false_answers = sum(record["predicted_answered"] for record in negatives)
    correct_abstentions = len(negatives) - false_answers
    exact_status = sum(record["status"] == record["expected_status"] for record in records)
    exact_reason = sum(record["reason"] == record["expected_reason"] for record in negatives)
    cited_records = [record for record in records if record["predicted_answered"]]
    citation_count = sum(record["citation_count"] for record in cited_records)
    relevant_citations = sum(record["relevant_citation_count"] for record in cited_records)
    valid_citations = sum(record["valid_citation_count"] for record in cited_records)
    correct_sources = sum(record["evidence_source_correct"] for record in positives)
    unsupported_claims = sum(record["unsupported_claim"] for record in cited_records)
    return {
        "total_cases": len(records),
        "supported_cases": len(positives),
        "unsupported_or_unsafe_cases": len(negatives),
        "answerability_accuracy": (true_answers + correct_abstentions) / (len(records) or 1),
        "correct_abstention_rate": correct_abstentions / (len(negatives) or 1),
        "false_answer_rate": false_answers / (len(negatives) or 1),
        "false_abstention_rate": false_abstentions / (len(positives) or 1),
        "exact_status_rate": exact_status / (len(records) or 1),
        "exact_abstention_reason_rate": exact_reason / (len(negatives) or 1),
        "citation_validity": valid_citations / (citation_count or 1),
        "citation_precision": relevant_citations / (citation_count or 1),
        "evidence_source_correctness": correct_sources / (len(positives) or 1),
        "unsupported_claim_rate": unsupported_claims / (len(cited_records) or 1),
        "structured_response_validity": sum(record["structured_valid"] for record in records) / (len(records) or 1),
        "average_answer_latency_ms": sum(record["latency_ms"] for record in records) / (len(records) or 1),
        "runtime_failure_count": sum(record["runtime_failure"] for record in records),
        "human_factual_review_required": true_answers,
    }


def evaluate_answers(
    dataset: AnswerEvaluationDataset,
    engine: EvidenceAnswerEngine,
    filters: RetrievalFilters,
    *,
    command: str,
    selected_split: str = "all",
) -> dict[str, Any]:
    if (filters.corpus_id, filters.access_policy, filters.authorization_reference) != (
        dataset.corpus_id, dataset.access_policy, dataset.authorization_reference
    ):
        raise RetrievalValidationError("answer evaluation base filters do not match the dataset")
    if selected_split not in {"all", "development", "held_out"}:
        raise RetrievalValidationError("selected answer-evaluation split is invalid")
    selected_cases = [case for case in dataset.cases if selected_split == "all" or case.split == selected_split]
    records: list[dict[str, Any]] = []
    for case in selected_cases:
        case_filters = replace(filters, **case.filter_override)
        try:
            response = engine.answer(case.question, filters=case_filters, mode="hybrid", top_k=5, candidate_k=20)
            mapping = response.to_mapping()
            predicted_answered = response.status == AnswerStatus.ANSWERED.value
            headings = [citation.heading_hierarchy[-1] if citation.heading_hierarchy else "" for citation in response.citations]
            relevant = sum(heading in case.expected_sections for heading in headings)
            validation = response.retrieval_metadata.get("citation_validation", {})
            exact_extract = response.answer == " ".join(citation.excerpt for citation in response.citations) if predicted_answered else True
            record = {
                "case_id": case.case_id,
                "split": case.split,
                "category": case.category,
                "question": case.question,
                "answerable": case.answerable,
                "expected_status": case.expected_status,
                "expected_reason": case.expected_reason,
                "expected_sections": list(case.expected_sections),
                "status": response.status,
                "reason": response.abstention_reason,
                "predicted_answered": predicted_answered,
                "answer": response.answer,
                "citation_count": len(response.citations),
                "valid_citation_count": len(response.citations) if validation.get("valid") else 0,
                "relevant_citation_count": relevant,
                "evidence_source_correct": predicted_answered and bool(headings) and all(heading in case.expected_sections for heading in headings),
                "unsupported_claim": predicted_answered and not exact_extract,
                "structured_valid": _structured_valid(response),
                "latency_ms": response.latency_ms,
                "runtime_failure": False,
                "response": mapping,
            }
        except Exception as exc:
            record = {
                "case_id": case.case_id, "split": case.split, "category": case.category,
                "question": case.question, "answerable": case.answerable,
                "expected_status": case.expected_status, "expected_reason": case.expected_reason,
                "expected_sections": list(case.expected_sections), "status": "runtime_failure",
                "reason": type(exc).__name__, "predicted_answered": False, "answer": None,
                "citation_count": 0, "valid_citation_count": 0, "relevant_citation_count": 0,
                "evidence_source_correct": False, "unsupported_claim": False,
                "structured_valid": False, "latency_ms": 0.0, "runtime_failure": True,
                "response": None,
            }
        records.append(record)
    active_splits = ("development", "held_out") if selected_split == "all" else (selected_split,)
    by_split = {split: [record for record in records if record["split"] == split] for split in active_splits}
    environment = engine.retriever.store.environment_info()
    return {
        "evaluation_dataset_version": dataset.dataset_version,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "actual_command": command,
        "selected_split": selected_split,
        "threshold_selection": {
            "procedure": "Configuration selected using development cases only; held_out labels are final evaluation only.",
            "configuration": engine.sufficiency_config.to_mapping(),
        },
        "corpus_id": dataset.corpus_id,
        "embedding_profile": engine.retriever.provider.metadata.to_mapping(),
        "postgresql_version": environment["postgresql_version"],
        "pgvector_version": environment["pgvector_version"],
        "metrics": {split: _metrics(split_records) for split, split_records in by_split.items()},
        "overall_metrics": _metrics(records),
        "metric_notes": {
            "factual_correctness": "Automatic checks verify expected source sections and exact extractive support; semantic correctness remains human-reviewable.",
            "unsupported_claim": "An answer is unsupported if it contains text beyond the concatenated validated excerpts.",
        },
        "per_case": records,
    }
