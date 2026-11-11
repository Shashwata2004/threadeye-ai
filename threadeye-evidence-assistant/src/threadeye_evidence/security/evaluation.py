"""Versioned adversarial and reliability evaluation with fixed expected outcomes."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.answering.models import AnswerStatus
from threadeye_evidence.retrieval.models import RetrievalFilters, RetrievalValidationError
from threadeye_evidence.security.faults import fault_engine


@dataclass(frozen=True)
class SecurityCase:
    case_id: str
    split: str
    question: str
    expected_status: str
    expected_reason: str | None
    category: str
    answerable: bool
    attack: bool
    fault: str | None
    filter_override: dict[str, str]


@dataclass(frozen=True)
class SecurityDataset:
    version: str
    labels_created_before_execution: bool
    cases: tuple[SecurityCase, ...]


def load_security_dataset(path: Path) -> SecurityDataset:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if raw.get("labels_created_before_execution") is not True:
        raise RetrievalValidationError("security labels must be fixed before execution")
    rows = raw.get("cases")
    if not isinstance(rows, list) or not 50 <= len(rows) <= 80:
        raise RetrievalValidationError("security evaluation requires 50 through 80 cases")
    cases: list[SecurityCase] = []
    for row in rows:
        override = row.get("filter_override", {})
        if not isinstance(override, dict) or any(key not in {"corpus_id", "access_policy", "authorization_reference", "document_classification"} for key in override):
            raise RetrievalValidationError("security filter override is invalid")
        cases.append(SecurityCase(
            row["case_id"], row["split"], row["question"], row["expected_status"],
            row.get("expected_reason"), row["category"], row["answerable"],
            row.get("attack", False), row.get("fault"), dict(override),
        ))
    if len({case.case_id for case in cases}) != len(cases):
        raise RetrievalValidationError("security case identifiers must be unique")
    if {case.split for case in cases} != {"development", "final_holdout"}:
        raise RetrievalValidationError("security data requires development and final_holdout splits")
    for split in ("development", "final_holdout"):
        if len([case for case in cases if case.split == split]) < 25:
            raise RetrievalValidationError("each security split requires at least 25 cases")
    return SecurityDataset(raw["dataset_version"], True, tuple(cases))


def _percentile95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, min(len(ordered) - 1, (95 * len(ordered) + 99) // 100 - 1))]


def _metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    positives = [row for row in records if row["answerable"]]
    negatives = [row for row in records if not row["answerable"]]
    injection_attacks = [row for row in records if row["category"] == "direct_injection"]
    faults = [row for row in records if row["fault"]]
    answered_positive = sum(row["status"] == "answered" for row in positives)
    false_answers = sum(row["status"] == "answered" for row in negatives)
    exact = sum(row["exact_outcome"] for row in records)
    citation_rows = [row for row in records if row["status"] == "answered"]
    latencies = [row["latency_ms"] for row in records]
    def ratio(numerator: int, denominator: int) -> dict[str, Any]:
        return {"numerator": numerator, "denominator": denominator, "rate": numerator / (denominator or 1)}
    return {
        "cases": len(records),
        "answerability_accuracy": ratio(answered_positive + len(negatives) - false_answers, len(records)),
        "correct_abstention": ratio(len(negatives) - false_answers, len(negatives)),
        "false_answer": ratio(false_answers, len(negatives)),
        "false_abstention": ratio(len(positives) - answered_positive, len(positives)),
        "citation_validity": ratio(sum(row["citation_valid"] for row in citation_rows), len(citation_rows)),
        "citation_source_correctness": ratio(sum(row["citation_source_correct"] for row in citation_rows), len(citation_rows)),
        "unsupported_claim": ratio(sum(row["unsupported_claim"] for row in citation_rows), len(citation_rows)),
        "authorization_violations": ratio(sum(row["authorization_violation"] for row in records), len(records)),
        "cross_corpus_leakage": ratio(sum(row["cross_corpus_leakage"] for row in records), len(records)),
        "prompt_injection_attack_success": ratio(
            sum(row["status"] == "answered" for row in injection_attacks), len(injection_attacks)
        ),
        "failure_mode_correctness": ratio(sum(row["exact_outcome"] for row in faults), len(faults)),
        "structured_error_correctness": ratio(sum(row["structured"] for row in negatives), len(negatives)),
        "exact_expected_outcome": ratio(exact, len(records)),
        "average_latency_ms": mean(latencies) if latencies else 0.0,
        "p95_latency_ms": _percentile95(latencies),
        "runtime_failures": sum(row["runtime_failure"] for row in records),
    }


def evaluate_security(dataset: SecurityDataset, engine: EvidenceAnswerEngine, filters: RetrievalFilters, *, selected_split: str, command: str) -> dict[str, Any]:
    if selected_split not in {"development", "final_holdout", "all"}:
        raise RetrievalValidationError("invalid security evaluation split")
    selected = [case for case in dataset.cases if selected_split == "all" or case.split == selected_split]
    records: list[dict[str, Any]] = []
    for case in selected:
        active_engine = fault_engine(engine, case.fault) if case.fault else engine
        active_filters = replace(filters, **case.filter_override)
        try:
            response = active_engine.answer(case.question, filters=active_filters, mode="hybrid", top_k=5, candidate_k=20)
            answered = response.status == AnswerStatus.ANSWERED.value
            citation_valid = answered and response.retrieval_metadata.get("citation_validation", {}).get("valid") is True
            source_correct = citation_valid and all(c.source_relative_path and c.chunk_id for c in response.citations)
            exact_extract = not answered or response.answer == " ".join(c.excerpt for c in response.citations)
            denied_scope_case = case.category in {"authorization", "cross_corpus"}
            records.append({
                "case_id": case.case_id, "split": case.split, "category": case.category,
                "answerable": case.answerable, "attack": case.attack, "fault": case.fault,
                "expected_status": case.expected_status, "expected_reason": case.expected_reason,
                "status": response.status, "reason": response.abstention_reason,
                "exact_outcome": response.status == case.expected_status and response.abstention_reason == case.expected_reason,
                "citation_valid": citation_valid, "citation_source_correct": source_correct,
                "unsupported_claim": answered and not exact_extract,
                "authorization_violation": answered and denied_scope_case,
                "cross_corpus_leakage": answered and case.category == "cross_corpus",
                "structured": (answered and bool(response.answer) and bool(response.citations)) or (not answered and response.answer is None and not response.citations and bool(response.abstention_reason)),
                "latency_ms": response.latency_ms, "runtime_failure": False,
            })
        except Exception as exc:
            records.append({
                "case_id": case.case_id, "split": case.split, "category": case.category,
                "answerable": case.answerable, "attack": case.attack, "fault": case.fault,
                "expected_status": case.expected_status, "expected_reason": case.expected_reason,
                "status": "runtime_failure", "reason": type(exc).__name__, "exact_outcome": False,
                "citation_valid": False, "citation_source_correct": False, "unsupported_claim": False,
                "authorization_violation": False, "cross_corpus_leakage": False,
                "structured": False, "latency_ms": 0.0, "runtime_failure": True,
            })
    splits = ("development", "final_holdout") if selected_split == "all" else (selected_split,)
    return {
        "evaluation_dataset_version": dataset.version,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "actual_command": command,
        "selected_split": selected_split,
        "labels_created_before_execution": dataset.labels_created_before_execution,
        "sufficiency_configuration": engine.sufficiency_config.to_mapping(),
        "metrics": {split: _metrics([row for row in records if row["split"] == split]) for split in splits},
        "overall_metrics": _metrics(records),
        "metric_scope": "Automated synthetic checks; factual semantic correctness still requires human review.",
        "per_case": records,
    }
