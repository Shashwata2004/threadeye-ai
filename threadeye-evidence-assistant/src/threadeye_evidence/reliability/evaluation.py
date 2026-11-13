"""Preregistered development and fresh-holdout answer-reliability evaluation."""

from __future__ import annotations

import hashlib
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
class ReliabilityCase:
    case_id: str
    split: str
    question: str
    answerable: bool
    expected_status: str
    expected_reason: str | None
    expected_sections: tuple[str, ...]
    expected_support_terms: tuple[str, ...]
    category: str
    notes: str
    filter_override: dict[str, str]


@dataclass(frozen=True)
class ReliabilityDataset:
    version: str
    sha256: str
    corpus_id: str
    access_policy: str
    authorization_reference: str
    source_relative_path: str
    authoring_method: str
    human_label_review: str
    cases: tuple[ReliabilityCase, ...]


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


def load_reliability_dataset(path: Path, *, historical_paths: Iterable[Path] = ()) -> ReliabilityDataset:
    raw_bytes = path.read_bytes()
    raw = json.loads(raw_bytes)
    if raw.get("labels_created_before_execution") is not True:
        raise RetrievalValidationError("reliability labels must be fixed before execution")
    if raw.get("threshold_tuning_permitted") is not False:
        raise RetrievalValidationError("reliability evaluation must forbid threshold tuning")
    if raw.get("fresh_holdout_single_primary_run") is not True:
        raise RetrievalValidationError("fresh holdout must declare a single primary run")
    rows = raw.get("cases")
    if not isinstance(rows, list) or not 20 <= len(rows) <= 30:
        raise RetrievalValidationError("reliability evaluation requires 20 through 30 cases")
    historical = _historical_questions(historical_paths)
    valid_statuses = {status.value for status in AnswerStatus}
    allowed_overrides = {"access_policy", "authorization_reference", "source_relative_path"}
    identifiers: set[str] = set()
    questions: set[str] = set()
    cases: list[ReliabilityCase] = []
    for row in rows:
        if not isinstance(row, dict):
            raise RetrievalValidationError("reliability cases must be objects")
        case_id = row.get("case_id")
        split = row.get("split")
        question = row.get("question")
        answerable = row.get("answerable")
        status = row.get("expected_status")
        reason = row.get("expected_reason")
        sections = row.get("expected_sections")
        terms = row.get("expected_support_terms")
        override = row.get("filter_override", {})
        if not isinstance(case_id, str) or not case_id or case_id in identifiers:
            raise RetrievalValidationError("reliability case IDs must be unique")
        if split not in {"development", "fresh_holdout"}:
            raise RetrievalValidationError("reliability split is invalid")
        if not isinstance(question, str) or not question.strip():
            raise RetrievalValidationError("reliability questions must be non-empty")
        normalized = _normalized_question(question)
        if normalized in questions or normalized in historical:
            raise RetrievalValidationError("reliability questions must not duplicate evaluation questions")
        if not isinstance(answerable, bool) or status not in valid_statuses:
            raise RetrievalValidationError("reliability answerability or expected status is invalid")
        if answerable != (status == AnswerStatus.ANSWERED.value):
            raise RetrievalValidationError("reliability answerability and status disagree")
        if answerable and reason is not None:
            raise RetrievalValidationError("answerable reliability cases cannot have a reason")
        if not answerable and (not isinstance(reason, str) or not reason):
            raise RetrievalValidationError("negative reliability cases require a reason")
        if not isinstance(sections, list) or any(not isinstance(value, str) or not value for value in sections):
            raise RetrievalValidationError("reliability sections are invalid")
        if not isinstance(terms, list) or any(not isinstance(value, str) or not value for value in terms):
            raise RetrievalValidationError("reliability support terms are invalid")
        if answerable != bool(sections) or answerable != bool(terms):
            raise RetrievalValidationError("positive reliability cases require sections and support terms")
        if any(not isinstance(row.get(name), str) or not row[name].strip() for name in ("category", "notes")):
            raise RetrievalValidationError("reliability category and notes are required")
        if not isinstance(override, dict) or any(key not in allowed_overrides for key in override):
            raise RetrievalValidationError("reliability filter override is invalid")
        identifiers.add(case_id)
        questions.add(normalized)
        cases.append(ReliabilityCase(
            case_id, split, question, answerable, status, reason, tuple(sections), tuple(terms),
            row["category"], row["notes"], dict(override),
        ))
    for split in ("development", "fresh_holdout"):
        selected = [case for case in cases if case.split == split]
        if len(selected) != 12 or sum(case.answerable for case in selected) != 6:
            raise RetrievalValidationError("each reliability split requires six positive and six negative cases")
    required = (
        "dataset_version", "corpus_id", "access_policy", "authorization_reference",
        "source_relative_path", "authoring_method", "human_label_review",
    )
    if any(not isinstance(raw.get(name), str) or not raw[name].strip() for name in required):
        raise RetrievalValidationError("reliability metadata is invalid")
    return ReliabilityDataset(
        raw["dataset_version"], hashlib.sha256(raw_bytes).hexdigest(), raw["corpus_id"],
        raw["access_policy"], raw["authorization_reference"], raw["source_relative_path"],
        raw["authoring_method"], raw["human_label_review"], tuple(cases),
    )


def _ratio(numerator: int, denominator: int) -> dict[str, int]:
    return {"numerator": numerator, "denominator": denominator}


def evaluate_reliability(
    dataset: ReliabilityDataset,
    engine: EvidenceAnswerEngine,
    filters: RetrievalFilters,
    *,
    selected_split: str,
    command: str,
    code_sha256: str,
) -> dict[str, Any]:
    if selected_split not in {"development", "fresh_holdout"}:
        raise RetrievalValidationError("select development or fresh_holdout")
    if (filters.corpus_id, filters.access_policy, filters.authorization_reference) != (
        dataset.corpus_id, dataset.access_policy, dataset.authorization_reference
    ):
        raise RetrievalValidationError("reliability filters do not match dataset metadata")
    records: list[dict[str, Any]] = []
    for case in (item for item in dataset.cases if item.split == selected_split):
        active_filters = replace(filters, **case.filter_override)
        try:
            response = engine.answer(case.question, filters=active_filters, mode="hybrid", top_k=5, candidate_k=20)
            answered = response.status == AnswerStatus.ANSWERED.value
            citations = [citation.to_mapping() for citation in response.citations]
            excerpts = " ".join(citation.excerpt for citation in response.citations).casefold()
            headings = [citation.heading_hierarchy[-1] if citation.heading_hierarchy else "" for citation in response.citations]
            citation_valid = answered and response.retrieval_metadata.get("citation_validation", {}).get("valid") is True
            source_correct = answered and bool(headings) and all(heading in case.expected_sections for heading in headings)
            terms_supported = answered and all(term.casefold() in excerpts for term in case.expected_support_terms)
            semantic_correct = (
                source_correct and terms_supported and citation_valid
                if case.answerable else not answered
            )
            unauthorized_scope = bool(case.filter_override) and response.status == AnswerStatus.UNAUTHORIZED.value
            auth_violation = bool(case.filter_override) and answered
            records.append({
                "case_id": case.case_id,
                "split": case.split,
                "category": case.category,
                "question": case.question,
                "answerable": case.answerable,
                "expected_status": case.expected_status,
                "expected_reason": case.expected_reason,
                "expected_sections": list(case.expected_sections),
                "expected_support_terms": list(case.expected_support_terms),
                "status": response.status,
                "reason": response.abstention_reason,
                "answer": response.answer,
                "answered": answered,
                "answerability_correct": answered == case.answerable,
                "exact_expected_outcome": response.status == case.expected_status and response.abstention_reason == case.expected_reason,
                "citation_integrity_valid": citation_valid if answered else True,
                "semantic_evidence_support_correct": semantic_correct,
                "source_section_correct": source_correct if answered else True,
                "support_terms_present": terms_supported if answered else True,
                "unsupported_claim": answered and not semantic_correct,
                "authorization_violation": auth_violation,
                "expected_unauthorized_scope_observed": unauthorized_scope,
                "retrieved_chunk_ids": list(response.retrieval_metadata.get("retrieved_chunk_ids", [])),
                "sufficiency": response.sufficiency.to_mapping() if response.sufficiency else None,
                "citations": citations,
                "authorization_context": {
                    "corpus_id": active_filters.corpus_id,
                    "access_policy": active_filters.access_policy,
                    "authorization_reference": active_filters.authorization_reference,
                },
                "latency_ms": response.latency_ms,
                "runtime_failure": False,
            })
        except Exception as exc:
            records.append({
                "case_id": case.case_id, "split": case.split, "category": case.category,
                "question": case.question, "answerable": case.answerable,
                "expected_status": case.expected_status, "expected_reason": case.expected_reason,
                "expected_sections": list(case.expected_sections),
                "expected_support_terms": list(case.expected_support_terms),
                "status": "runtime_failure", "reason": type(exc).__name__, "answer": None,
                "answered": False, "answerability_correct": False, "exact_expected_outcome": False,
                "citation_integrity_valid": False, "semantic_evidence_support_correct": False,
                "source_section_correct": False, "support_terms_present": False,
                "unsupported_claim": False, "authorization_violation": False,
                "expected_unauthorized_scope_observed": False, "retrieved_chunk_ids": [],
                "sufficiency": None, "citations": [], "authorization_context": {},
                "latency_ms": 0.0, "runtime_failure": True,
            })
    positives = [row for row in records if row["answerable"]]
    negatives = [row for row in records if not row["answerable"]]
    answered_rows = [row for row in records if row["answered"]]
    return {
        "evaluation_dataset_version": dataset.version,
        "evaluation_dataset_sha256": dataset.sha256,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "selected_split": selected_split,
        "actual_command": command,
        "corrective_code_sha256": code_sha256,
        "labels_created_before_execution": True,
        "threshold_tuning_permitted": False,
        "historical_benchmarks_modified": False,
        "authoring_method": dataset.authoring_method,
        "human_label_review": dataset.human_label_review,
        "metrics": {
            "cases": len(records),
            "overall_answerability_accuracy": _ratio(sum(row["answerability_correct"] for row in records), len(records)),
            "correct_abstention_rate": _ratio(sum(not row["answered"] for row in negatives), len(negatives)),
            "false_answer_rate": _ratio(sum(row["answered"] for row in negatives), len(negatives)),
            "false_abstention_rate": _ratio(sum(not row["answered"] for row in positives), len(positives)),
            "citation_validity": _ratio(sum(row["citation_integrity_valid"] for row in answered_rows), len(answered_rows)),
            "semantic_evidence_support_correctness": _ratio(sum(row["semantic_evidence_support_correct"] for row in records), len(records)),
            "authorization_violation_rate": _ratio(sum(row["authorization_violation"] for row in records), len(records)),
            "unsupported_claim_rate": _ratio(sum(row["unsupported_claim"] for row in records), len(records)),
            "positive_answer_coverage": _ratio(sum(row["answered"] for row in positives), len(positives)),
            "exact_expected_outcome": _ratio(sum(row["exact_expected_outcome"] for row in records), len(records)),
            "runtime_failures": sum(row["runtime_failure"] for row in records),
            "average_latency_ms": sum(row["latency_ms"] for row in records) / (len(records) or 1),
        },
        "interpretation_limits": [
            "The sample is small and synthetic; confidence intervals would be wide.",
            "The automatically authored labels did not receive independent human review.",
            "Results do not estimate accuracy on factory production data.",
        ],
        "per_case": records,
    }
