"""Independent, pre-labeled synthetic holdout evaluation for Prompt 11."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.answering.models import AnswerStatus
from threadeye_evidence.retrieval.models import RetrievalFilters, RetrievalValidationError


@dataclass(frozen=True)
class QAHoldoutCase:
    case_id: str
    question: str
    answerable: bool
    expected_status: str
    expected_sections: tuple[str, ...]
    expected_reason: str | None
    category: str
    human_semantic_review_required: bool
    notes: str
    filter_override: dict[str, str]


@dataclass(frozen=True)
class QAHoldoutDataset:
    version: str
    corpus_id: str
    access_policy: str
    authorization_reference: str
    source_relative_path: str
    cases: tuple[QAHoldoutCase, ...]


def _normalized_question(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()


def _historical_questions(paths: Iterable[Path]) -> set[str]:
    questions: set[str] = set()
    for path in paths:
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = raw.get("cases", raw.get("queries", []))
        if not isinstance(rows, list):
            raise RetrievalValidationError("historical evaluation rows are invalid")
        for row in rows:
            if isinstance(row, dict):
                question = row.get("question", row.get("query"))
                if isinstance(question, str):
                    questions.add(_normalized_question(question))
    return questions


def load_qa_holdout(path: Path, *, historical_paths: Iterable[Path] = ()) -> QAHoldoutDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("labels_created_before_execution") is not True:
        raise RetrievalValidationError("QA holdout labels must be fixed before execution")
    if raw.get("threshold_tuning_permitted") is not False:
        raise RetrievalValidationError("QA holdout must forbid threshold tuning")
    rows = raw.get("cases")
    if not isinstance(rows, list) or len(rows) != 10:
        raise RetrievalValidationError("QA holdout requires exactly 10 cases")
    valid_statuses = {status.value for status in AnswerStatus}
    allowed_overrides = {"access_policy", "authorization_reference", "source_relative_path"}
    historical = _historical_questions(historical_paths)
    identifiers: set[str] = set()
    questions: set[str] = set()
    cases: list[QAHoldoutCase] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RetrievalValidationError("QA holdout cases must be objects")
        case_id = row.get("case_id")
        question = row.get("question")
        answerable = row.get("answerable")
        expected_status = row.get("expected_status")
        expected_sections = row.get("expected_sections")
        expected_reason = row.get("expected_reason")
        override = row.get("filter_override", {})
        if not isinstance(case_id, str) or not case_id or case_id in identifiers:
            raise RetrievalValidationError("QA holdout case IDs must be unique")
        if not isinstance(question, str) or not question.strip():
            raise RetrievalValidationError("QA holdout questions must be non-empty")
        normalized = _normalized_question(question)
        if normalized in questions or normalized in historical:
            raise RetrievalValidationError("QA holdout questions must not duplicate benchmark questions")
        if not isinstance(answerable, bool) or expected_status not in valid_statuses:
            raise RetrievalValidationError("QA holdout answerability or expected status is invalid")
        if answerable != (expected_status == AnswerStatus.ANSWERED.value):
            raise RetrievalValidationError("QA holdout answerability and expected status disagree")
        if not isinstance(expected_sections, list) or any(not isinstance(value, str) or not value for value in expected_sections):
            raise RetrievalValidationError("QA holdout expected sections are invalid")
        if answerable != bool(expected_sections):
            raise RetrievalValidationError("QA holdout positives require sections and negatives forbid them")
        if answerable and expected_reason is not None:
            raise RetrievalValidationError("QA holdout positives cannot have an abstention reason")
        if not answerable and (not isinstance(expected_reason, str) or not expected_reason):
            raise RetrievalValidationError("QA holdout negatives require an abstention reason")
        if row.get("human_semantic_review_required") is not True:
            raise RetrievalValidationError("every QA holdout case requires human semantic review")
        if any(not isinstance(row.get(name), str) or not row[name].strip() for name in ("category", "notes")):
            raise RetrievalValidationError("QA holdout category and notes are required")
        if not isinstance(override, dict) or any(key not in allowed_overrides for key in override):
            raise RetrievalValidationError("QA holdout filter override is invalid")
        if any(not isinstance(value, str) or not value for value in override.values()):
            raise RetrievalValidationError("QA holdout filter override values must be non-empty strings")
        identifiers.add(case_id)
        questions.add(normalized)
        cases.append(QAHoldoutCase(
            case_id, question, answerable, expected_status, tuple(expected_sections), expected_reason,
            row["category"], True, row["notes"], dict(override),
        ))
    if sum(case.answerable for case in cases) != 5:
        raise RetrievalValidationError("QA holdout requires five positive and five negative cases")
    required = ("dataset_version", "corpus_id", "access_policy", "authorization_reference", "source_relative_path")
    if any(not isinstance(raw.get(name), str) or not raw[name].strip() for name in required):
        raise RetrievalValidationError("QA holdout metadata is invalid")
    return QAHoldoutDataset(
        raw["dataset_version"], raw["corpus_id"], raw["access_policy"],
        raw["authorization_reference"], raw["source_relative_path"], tuple(cases),
    )


def evaluate_qa_holdout(
    dataset: QAHoldoutDataset,
    engine: EvidenceAnswerEngine,
    filters: RetrievalFilters,
    *,
    command: str,
) -> dict[str, Any]:
    if (filters.corpus_id, filters.access_policy, filters.authorization_reference) != (
        dataset.corpus_id, dataset.access_policy, dataset.authorization_reference
    ):
        raise RetrievalValidationError("QA holdout filters do not match dataset metadata")
    records: list[dict[str, Any]] = []
    for case in dataset.cases:
        active_filters = replace(filters, **case.filter_override)
        try:
            response = engine.answer(case.question, filters=active_filters, mode="hybrid", top_k=5, candidate_k=20)
            answered = response.status == AnswerStatus.ANSWERED.value
            headings = [citation.heading_hierarchy[-1] if citation.heading_hierarchy else "" for citation in response.citations]
            citation_validation = response.retrieval_metadata.get("citation_validation", {})
            citation_valid = answered and citation_validation.get("valid") is True
            exact_extract = not answered or response.answer == " ".join(citation.excerpt for citation in response.citations)
            records.append({
                "case_id": case.case_id,
                "category": case.category,
                "answerable": case.answerable,
                "expected_status": case.expected_status,
                "expected_reason": case.expected_reason,
                "expected_sections": list(case.expected_sections),
                "status": response.status,
                "reason": response.abstention_reason,
                "exact_expected_outcome": response.status == case.expected_status and response.abstention_reason == case.expected_reason,
                "answered": answered,
                "citation_count": len(response.citations),
                "citations_valid": citation_valid if answered else True,
                "expected_source_section": answered and bool(headings) and all(heading in case.expected_sections for heading in headings),
                "unsupported_claim": answered and not exact_extract,
                "latency_ms": response.latency_ms,
                "runtime_failure": False,
                "human_semantic_review_required": case.human_semantic_review_required,
            })
        except Exception as exc:
            records.append({
                "case_id": case.case_id, "category": case.category, "answerable": case.answerable,
                "expected_status": case.expected_status, "expected_reason": case.expected_reason,
                "expected_sections": list(case.expected_sections), "status": "runtime_failure",
                "reason": type(exc).__name__, "exact_expected_outcome": False, "answered": False,
                "citation_count": 0, "citations_valid": False, "expected_source_section": False,
                "unsupported_claim": False, "latency_ms": 0.0, "runtime_failure": True,
                "human_semantic_review_required": case.human_semantic_review_required,
            })
    positives = [record for record in records if record["answerable"]]
    negatives = [record for record in records if not record["answerable"]]
    exact = sum(record["exact_expected_outcome"] for record in records)
    false_answers = sum(record["answered"] for record in negatives)
    false_abstentions = sum(not record["answered"] for record in positives)
    answered_records = [record for record in records if record["answered"]]
    return {
        "evaluation_dataset_version": dataset.version,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "actual_command": command,
        "labels_created_before_execution": True,
        "threshold_tuning_permitted": False,
        "historical_benchmarks_modified": False,
        "corpus_id": dataset.corpus_id,
        "metrics": {
            "cases": len(records),
            "positive_cases": len(positives),
            "negative_cases": len(negatives),
            "exact_expected_outcome": {"numerator": exact, "denominator": len(records)},
            "false_answer_rate": {"numerator": false_answers, "denominator": len(negatives)},
            "false_abstention_rate": {"numerator": false_abstentions, "denominator": len(positives)},
            "citation_validity": {
                "numerator": sum(record["citations_valid"] for record in answered_records),
                "denominator": len(answered_records),
            },
            "source_section_correctness": {
                "numerator": sum(record["expected_source_section"] for record in answered_records),
                "denominator": len(answered_records),
            },
            "unsupported_claims": sum(record["unsupported_claim"] for record in records),
            "runtime_failures": sum(record["runtime_failure"] for record in records),
            "average_latency_ms": sum(record["latency_ms"] for record in records) / (len(records) or 1),
        },
        "human_review": {
            "required_cases": len(records),
            "completed_cases": 0,
            "status": "manual factual/semantic review pending",
        },
        "per_case": records,
    }
