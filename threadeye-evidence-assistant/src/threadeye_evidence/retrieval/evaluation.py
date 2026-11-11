"""Fixed-label retrieval evaluation for keyword, vector, and hybrid modes."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from threadeye_evidence.retrieval.engine import HybridRetriever
from threadeye_evidence.retrieval.fusion import RRFConfig
from threadeye_evidence.retrieval.models import RetrievalFilters, RetrievalMode, RetrievalValidationError


@dataclass(frozen=True)
class EvaluationQuery:
    query_id: str
    query: str
    expected_sections: tuple[str, ...]
    relevance_criteria: str
    category: str
    notes: str
    expected_no_result: bool


@dataclass(frozen=True)
class EvaluationDataset:
    dataset_version: str
    corpus_id: str
    access_policy: str
    authorization_reference: str
    source_relative_path: str
    queries: tuple[EvaluationQuery, ...]


def load_evaluation_dataset(path: Path) -> EvaluationDataset:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("created_before_prediction_review") is not True:
        raise RetrievalValidationError("evaluation dataset must declare pre-prediction label creation")
    required = ("dataset_version", "corpus_id", "access_policy", "authorization_reference", "source_relative_path")
    for field_name in required:
        if not isinstance(raw.get(field_name), str) or not raw[field_name].strip():
            raise RetrievalValidationError(f"evaluation dataset {field_name} is invalid")
    query_rows = raw.get("queries")
    if not isinstance(query_rows, list) or not 30 <= len(query_rows) <= 50:
        raise RetrievalValidationError("evaluation dataset must contain 30 through 50 queries")
    queries: list[EvaluationQuery] = []
    identifiers: set[str] = set()
    for row in query_rows:
        if not isinstance(row, dict):
            raise RetrievalValidationError("every evaluation query must be an object")
        query_id = row.get("query_id")
        if not isinstance(query_id, str) or not query_id.strip() or query_id in identifiers:
            raise RetrievalValidationError("evaluation query IDs must be unique non-empty strings")
        identifiers.add(query_id)
        expected = row.get("expected_sections")
        if not isinstance(expected, list) or any(not isinstance(item, str) or not item.strip() for item in expected):
            raise RetrievalValidationError("expected_sections must be a list of non-empty strings")
        expected_no_result = row.get("expected_no_result")
        if not isinstance(expected_no_result, bool) or expected_no_result != (len(expected) == 0):
            raise RetrievalValidationError("expected_no_result must exactly match whether relevant sections are empty")
        string_fields = ("query", "relevance_criteria", "category", "notes")
        if any(not isinstance(row.get(name), str) or not row[name].strip() for name in string_fields):
            raise RetrievalValidationError("evaluation query text fields must be non-empty strings")
        queries.append(
            EvaluationQuery(
                query_id,
                row["query"],
                tuple(expected),
                row["relevance_criteria"],
                row["category"],
                row["notes"],
                expected_no_result,
            )
        )
    return EvaluationDataset(
        raw["dataset_version"],
        raw["corpus_id"],
        raw["access_policy"],
        raw["authorization_reference"],
        raw["source_relative_path"],
        tuple(queries),
    )


def _section(result: dict[str, Any]) -> str:
    headings = result["heading_hierarchy"]
    return headings[-1] if headings else ""


def _mode_metrics(records: list[dict[str, Any]], relevant_query_count: int, no_result_count: int) -> dict[str, Any]:
    hit_at = {1: 0, 3: 0, 5: 0}
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0
    no_result_correct = 0
    failures = 0
    latency_sum = 0.0
    successful = 0
    for record in records:
        if record["failure"] is not None:
            failures += 1
            continue
        successful += 1
        latency_sum += record["latency_ms"]
        expected = set(record["expected_sections"])
        returned = record["returned_sections"]
        if not expected:
            if not returned:
                no_result_correct += 1
            continue
        relevant_flags = [section in expected for section in returned]
        for cutoff in hit_at:
            if any(relevant_flags[:cutoff]):
                hit_at[cutoff] += 1
        retrieved_relevant = set(returned[:5]) & expected
        recall_sum += len(retrieved_relevant) / len(expected)
        first_rank = next((index for index, relevant in enumerate(relevant_flags, start=1) if relevant), None)
        if first_rank is not None:
            reciprocal_rank_sum += 1.0 / first_rank
    denominator = relevant_query_count or 1
    return {
        "hit_rate_at_1": hit_at[1] / denominator,
        "hit_rate_at_3": hit_at[3] / denominator,
        "hit_rate_at_5": hit_at[5] / denominator,
        "recall_at_5": recall_sum / denominator,
        "mrr": reciprocal_rank_sum / denominator,
        "no_result_accuracy": no_result_correct / (no_result_count or 1),
        "expected_no_result_queries": no_result_count,
        "average_query_latency_ms": latency_sum / (successful or 1),
        "per_query_failure_count": failures,
        "evaluated_queries": len(records),
    }


def evaluate_retrieval(
    dataset: EvaluationDataset,
    retriever: HybridRetriever,
    filters: RetrievalFilters,
    *,
    rrf_config: RRFConfig,
    command: str,
) -> dict[str, Any]:
    if filters.corpus_id != dataset.corpus_id or filters.access_policy != dataset.access_policy:
        raise RetrievalValidationError("evaluation filters do not match the fixed dataset authorization scope")
    if filters.authorization_reference != dataset.authorization_reference:
        raise RetrievalValidationError("evaluation authorization reference does not match the dataset")
    modes = (RetrievalMode.KEYWORD, RetrievalMode.VECTOR, RetrievalMode.HYBRID)
    by_mode: dict[str, list[dict[str, Any]]] = {mode.value: [] for mode in modes}
    corpus_versions: set[str] = set()
    for item in dataset.queries:
        for mode in modes:
            try:
                response = retriever.search(
                    item.query,
                    mode=mode,
                    filters=filters,
                    top_k=5,
                    candidate_k=20,
                    rrf_config=rrf_config,
                )
                mapped_results = [result.to_mapping() for result in response.results]
                corpus_versions.update(result["corpus_version"] for result in mapped_results)
                record = {
                    "query_id": item.query_id,
                    "query": item.query,
                    "category": item.category,
                    "expected_sections": list(item.expected_sections),
                    "expected_no_result": item.expected_no_result,
                    "returned_chunk_ids": [result["chunk_id"] for result in mapped_results],
                    "returned_sections": [_section(result) for result in mapped_results],
                    "latency_ms": response.latency_ms,
                    "backend_status": response.backend_status,
                    "failure": None,
                }
            except Exception as exc:
                record = {
                    "query_id": item.query_id,
                    "query": item.query,
                    "category": item.category,
                    "expected_sections": list(item.expected_sections),
                    "expected_no_result": item.expected_no_result,
                    "returned_chunk_ids": [],
                    "returned_sections": [],
                    "latency_ms": 0.0,
                    "backend_status": {},
                    "failure": type(exc).__name__,
                }
            by_mode[mode.value].append(record)

    relevant_count = sum(not item.expected_no_result for item in dataset.queries)
    no_result_count = len(dataset.queries) - relevant_count
    metrics = {
        mode.value: _mode_metrics(by_mode[mode.value], relevant_count, no_result_count)
        for mode in modes
    }
    environment = retriever.store.environment_info()
    return {
        "evaluation_dataset_version": dataset.dataset_version,
        "evaluation_timestamp": datetime.now(timezone.utc).isoformat(),
        "actual_command": command,
        "corpus_id": dataset.corpus_id,
        "corpus_versions": sorted(corpus_versions),
        "query_count": len(dataset.queries),
        "relevant_query_count": relevant_count,
        "expected_no_result_query_count": no_result_count,
        "embedding_profile": retriever.provider.metadata.to_mapping(),
        "postgresql_version": environment["postgresql_version"],
        "pgvector_version": environment["pgvector_version"],
        "rrf_config": rrf_config.to_mapping(),
        "metric_definitions": {
            "hit_rate_at_k": "fraction of queries with relevant labels having at least one relevant result in top k",
            "recall_at_5": "mean fraction of each query's labeled relevant sections retrieved in top 5",
            "mrr": "mean reciprocal rank of the first relevant result over queries with relevant labels",
            "no_result_accuracy": "fraction of expected-no-result queries returning zero chunks",
            "average_query_latency_ms": "mean in-process retrieval latency for successful queries",
        },
        "metrics": metrics,
        "per_query": by_mode,
    }
