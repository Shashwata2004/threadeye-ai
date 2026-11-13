"""Command-line entry point for evidence ingestion, indexing, and retrieval."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from threadeye_evidence.answering.abstention import SufficiencyConfig
from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.answering.evaluation import evaluate_answers, load_answer_evaluation_dataset
from threadeye_evidence.config import InventoryConfig
from threadeye_evidence.corpus.allowlist import load_manifest
from threadeye_evidence.corpus.chunking import ChunkConfig
from threadeye_evidence.corpus.ingestion import ingest_document
from threadeye_evidence.corpus.inventory import inventory_documents
from threadeye_evidence.corpus.output import write_sanitized_snapshot
from threadeye_evidence.corpus.safety import SafetyViolation
from threadeye_evidence.corpus.sanitization import SanitizationRejected
from threadeye_evidence.retrieval.engine import HybridRetriever, RetrievalBackendError
from threadeye_evidence.retrieval.evaluation import evaluate_retrieval, load_evaluation_dataset
from threadeye_evidence.retrieval.fusion import RRFConfig
from threadeye_evidence.retrieval.models import RetrievalFilters, RetrievalMode, RetrievalValidationError
from threadeye_evidence.retrieval.policy import SECURITY_EVALUATION_POLICY, SYNTHETIC_EVALUATION_POLICY
from threadeye_evidence.retrieval.store import RetrievalStore
from threadeye_evidence.qa.evaluation import evaluate_qa_holdout, load_qa_holdout
from threadeye_evidence.security.evaluation import evaluate_security, load_security_dataset
from threadeye_evidence.vector.database import DatabaseSafetyError, DatabaseSettings, EvidenceDatabase
from threadeye_evidence.vector.embeddings import EmbeddingValidationError, FastEmbedProvider
from threadeye_evidence.vector.indexing import default_migrations_dir, index_ingestion_result
from threadeye_evidence.vector.provenance import ProvenanceValidationError


def _add_vector_options(parser: argparse.ArgumentParser, *, database: bool = True) -> None:
    parser.add_argument(
        "--model-cache",
        type=Path,
        default=Path(os.environ.get("THREADEYE_EVIDENCE_MODEL_CACHE", "build/model-cache")),
        help="ignored local cache for the one pinned embedding model",
    )
    parser.add_argument("--offline-model", action="store_true", help="require the pinned model to be cached")
    if database:
        parser.add_argument(
            "--database-url",
            default=os.environ.get("THREADEYE_EVIDENCE_DATABASE_URL"),
            help="loopback-only isolated database URL (or THREADEYE_EVIDENCE_DATABASE_URL)",
        )


def _database(value: str | None) -> EvidenceDatabase:
    if value is None:
        raise DatabaseSafetyError("set THREADEYE_EVIDENCE_DATABASE_URL or pass --database-url")
    return EvidenceDatabase(DatabaseSettings.from_dsn(value), migrations_dir=default_migrations_dir())


def _provider(args: argparse.Namespace) -> FastEmbedProvider:
    return FastEmbedProvider(args.model_cache, local_files_only=args.offline_model)


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _add_retrieval_filters(parser: argparse.ArgumentParser) -> None:
    policy = SYNTHETIC_EVALUATION_POLICY
    parser.add_argument("--corpus-id", default=policy.corpus_id)
    parser.add_argument("--access-policy", default=policy.access_policy)
    parser.add_argument("--authorization-reference", default="PROMPT-04-SYNTHETIC-VECTOR-FIXTURE")
    parser.add_argument("--source-relative-path")
    parser.add_argument("--source-sha256")
    parser.add_argument("--corpus-version")
    parser.add_argument("--processing-version")
    parser.add_argument("--document-classification", default=policy.document_classification)


def _retrieval_filters(args: argparse.Namespace) -> RetrievalFilters:
    return RetrievalFilters(
        args.corpus_id,
        args.access_policy,
        args.authorization_reference,
        args.source_relative_path,
        args.source_sha256,
        args.corpus_version,
        args.processing_version,
        args.document_classification,
    )


def _retriever(args: argparse.Namespace) -> HybridRetriever:
    provider = _provider(args)
    database = _database(args.database_url)
    database.migrate()
    return HybridRetriever(RetrievalStore(database), provider)


def _sufficiency_config(args: argparse.Namespace) -> SufficiencyConfig:
    return SufficiencyConfig(
        version="prompt11r-v1",
        min_semantic_similarity=args.min_semantic_similarity,
        strong_semantic_similarity=args.strong_semantic_similarity,
        min_semantic_margin=args.min_semantic_margin,
    )


def _add_sufficiency_options(parser: argparse.ArgumentParser) -> None:
    defaults = SufficiencyConfig()
    parser.add_argument("--min-semantic-similarity", type=float, default=defaults.min_semantic_similarity)
    parser.add_argument("--strong-semantic-similarity", type=float, default=defaults.strong_semantic_similarity)
    parser.add_argument("--min-semantic-margin", type=float, default=defaults.min_semantic_margin)


def _print_search_summary(payload: dict[str, object]) -> None:
    print(f"mode={payload['mode']} results={payload['result_count']} latency_ms={payload['latency_ms']:.3f}")
    print(f"backends={json.dumps(payload['backend_status'], sort_keys=True)}")
    for result in payload["results"]:
        headings = " > ".join(result["heading_hierarchy"])
        print(
            f"{result['final_rank']}. {result['chunk_id']} | {headings} | "
            f"methods={','.join(result['retrieval_methods'])} | "
            f"keyword_rank={result['keyword_rank']} vector_rank={result['vector_rank']} "
            f"rrf={result['rrf_score']}"
        )


def _print_evaluation_summary(report: dict[str, object]) -> None:
    print(f"dataset={report['evaluation_dataset_version']} queries={report['query_count']}")
    for mode, metrics in report["metrics"].items():
        print(
            f"{mode}: Hit@1={metrics['hit_rate_at_1']:.3f} "
            f"Hit@3={metrics['hit_rate_at_3']:.3f} Hit@5={metrics['hit_rate_at_5']:.3f} "
            f"Recall@5={metrics['recall_at_5']:.3f} MRR={metrics['mrr']:.3f} "
            f"NoResult={metrics['no_result_accuracy']:.3f} "
            f"AvgMs={metrics['average_query_latency_ms']:.3f} "
            f"Failures={metrics['per_query_failure_count']}"
        )


def _print_answer_summary(payload: dict[str, object]) -> None:
    print(f"status={payload['status']} mode={payload['answer_mode']} latency_ms={payload['latency_ms']:.3f}")
    if payload["answer"]:
        print(payload["answer"])
        for index, citation in enumerate(payload["citations"], start=1):
            heading = " > ".join(citation["heading_hierarchy"])
            print(f"[{index}] {citation['source_relative_path']} | {heading} | chunk={citation['chunk_id']}")
    else:
        print(f"abstained={payload['abstention_reason']}")


def _print_answer_evaluation_summary(report: dict[str, object]) -> None:
    print(f"dataset={report['evaluation_dataset_version']}")
    for split, metrics in report["metrics"].items():
        print(
            f"{split}: cases={metrics['total_cases']} answerability={metrics['answerability_accuracy']:.3f} "
            f"correct_abstention={metrics['correct_abstention_rate']:.3f} "
            f"false_answer={metrics['false_answer_rate']:.3f} false_abstention={metrics['false_abstention_rate']:.3f} "
            f"citation_validity={metrics['citation_validity']:.3f} citation_precision={metrics['citation_precision']:.3f} "
            f"source_correctness={metrics['evidence_source_correctness']:.3f} "
            f"unsupported_claim={metrics['unsupported_claim_rate']:.3f} "
            f"structured={metrics['structured_response_validity']:.3f} avg_ms={metrics['average_answer_latency_ms']:.3f}"
        )


def _print_security_evaluation_summary(report: dict[str, object]) -> None:
    print(f"dataset={report['evaluation_dataset_version']} split={report['selected_split']}")
    for split, metrics in report["metrics"].items():
        exact = metrics["exact_expected_outcome"]
        attack = metrics["prompt_injection_attack_success"]
        failures = metrics["failure_mode_correctness"]
        print(
            f"{split}: cases={metrics['cases']} exact={exact['numerator']}/{exact['denominator']} "
            f"attack_success={attack['numerator']}/{attack['denominator']} "
            f"failure_correct={failures['numerator']}/{failures['denominator']} "
            f"avg_ms={metrics['average_latency_ms']:.3f} p95_ms={metrics['p95_latency_ms']:.3f} "
            f"runtime_failures={metrics['runtime_failures']}"
        )


def _print_qa_evaluation_summary(report: dict[str, object]) -> None:
    metrics = report["metrics"]
    exact = metrics["exact_expected_outcome"]
    false_answers = metrics["false_answer_rate"]
    false_abstentions = metrics["false_abstention_rate"]
    citations = metrics["citation_validity"]
    print(f"dataset={report['evaluation_dataset_version']} cases={metrics['cases']}")
    print(
        f"exact={exact['numerator']}/{exact['denominator']} "
        f"false_answers={false_answers['numerator']}/{false_answers['denominator']} "
        f"false_abstentions={false_abstentions['numerator']}/{false_abstentions['denominator']} "
        f"citation_validity={citations['numerator']}/{citations['denominator']} "
        f"avg_ms={metrics['average_latency_ms']:.3f} runtime_failures={metrics['runtime_failures']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ThreadEye isolated evidence inventory and retrieval")
    subparsers = parser.add_subparsers(dest="command", required=True)
    inventory = subparsers.add_parser("inventory", help="inventory exact manifest-approved documents")
    inventory.add_argument("--source-root", required=True, type=Path, help="trusted operator-configured ThreadEye root")
    inventory.add_argument(
        "--manifest",
        type=Path,
        default=Path("knowledge/manifest.json"),
        help="companion-project allowlist manifest",
    )
    ingest = subparsers.add_parser("ingest", help="sanitize and chunk one exact authorized manifest document")
    ingest.add_argument("--source-root", type=Path, default=Path("examples/synthetic"))
    ingest.add_argument("--manifest", type=Path, default=Path("knowledge/synthetic-manifest.json"))
    ingest.add_argument("--document", default="demo.md", help="exact path already present in the manifest")
    ingest.add_argument("--intended-use", default="prompt03_synthetic_demo")
    ingest.add_argument("--target-chars", type=int, default=800)
    ingest.add_argument("--max-chars", type=int, default=1200)
    ingest.add_argument("--write-output", action="store_true", help="write an ignored sanitized snapshot")
    model_info = subparsers.add_parser("model-info", help="show the pinned genuine embedding profile")
    _add_vector_options(model_info, database=False)
    model_info.add_argument("--verify", action="store_true", help="load the model and execute a real embedding")

    index = subparsers.add_parser("index", help="index one authorized sanitized synthetic document")
    index.add_argument("--source-root", type=Path, default=Path("examples/synthetic"))
    index.add_argument("--manifest", type=Path, default=Path("knowledge/synthetic-manifest.json"))
    index.add_argument("--document", default="technical-evidence.md")
    index.add_argument("--intended-use", default="prompt04_synthetic_vector_index")
    index.add_argument("--target-chars", type=int, default=300)
    index.add_argument("--max-chars", type=int, default=600)
    index.add_argument("--batch-size", type=int, default=8)
    _add_vector_options(index)

    security_index = subparsers.add_parser(
        "index-security-fixtures", help="index only the exact approved Prompt 07 fictional security fixtures"
    )
    security_index.add_argument("--source-root", type=Path, default=Path("examples/synthetic"))
    security_index.add_argument("--manifest", type=Path, default=Path("knowledge/synthetic-manifest.json"))
    security_index.add_argument("--batch-size", type=int, default=8)
    _add_vector_options(security_index)

    status = subparsers.add_parser("index-status", help="show isolated pgvector index status")
    _add_vector_options(status)

    query = subparsers.add_parser("query", help="run exact cosine search over sanitized synthetic chunks")
    query.add_argument("query_text", help="non-empty synthetic verification query")
    query.add_argument("--top-k", type=int, default=5)
    _add_vector_options(query)

    search = subparsers.add_parser("search", help="run authorized keyword, vector, or hybrid retrieval")
    search.add_argument("--mode", choices=[mode.value for mode in RetrievalMode], required=True)
    search.add_argument("--query", required=True, help="non-empty query, at most 1000 characters")
    search.add_argument("--top-k", type=int, default=5)
    search.add_argument("--candidate-k", type=int, default=20)
    search.add_argument("--rrf-k", type=float, default=60.0)
    search.add_argument("--keyword-weight", type=float, default=1.0)
    search.add_argument("--vector-weight", type=float, default=1.0)
    search.add_argument("--format", choices=("json", "summary"), default="json")
    _add_retrieval_filters(search)
    _add_vector_options(search)

    evaluate = subparsers.add_parser("evaluate-retrieval", help="benchmark all three retrieval modes")
    evaluate.add_argument("--dataset", type=Path, default=_project_root() / "evaluation/retrieval-v1.json")
    evaluate.add_argument("--rrf-k", type=float, default=60.0)
    evaluate.add_argument("--keyword-weight", type=float, default=1.0)
    evaluate.add_argument("--vector-weight", type=float, default=1.0)
    evaluate.add_argument("--format", choices=("json", "summary"), default="summary")
    _add_retrieval_filters(evaluate)
    _add_vector_options(evaluate)

    answer = subparsers.add_parser("answer-evidence", help="answer from authorized evidence or explicitly abstain")
    answer.add_argument("--question", required=True)
    answer.add_argument("--mode", choices=[mode.value for mode in RetrievalMode], default="hybrid")
    answer.add_argument("--top-k", type=int, default=5)
    answer.add_argument("--candidate-k", type=int, default=20)
    answer.add_argument("--rrf-k", type=float, default=60.0)
    answer.add_argument("--keyword-weight", type=float, default=1.0)
    answer.add_argument("--vector-weight", type=float, default=1.0)
    answer.add_argument("--format", choices=("json", "summary"), default="summary")
    _add_retrieval_filters(answer)
    _add_sufficiency_options(answer)
    _add_vector_options(answer)

    answer_eval = subparsers.add_parser("evaluate-answers", help="evaluate answerability, abstention, and citations")
    answer_eval.add_argument("--dataset", type=Path, default=_project_root() / "evaluation/answering-v1.json")
    answer_eval.add_argument("--split", choices=("development", "held_out", "all"), default="held_out")
    answer_eval.add_argument("--format", choices=("json", "summary"), default="summary")
    _add_retrieval_filters(answer_eval)
    _add_sufficiency_options(answer_eval)
    _add_vector_options(answer_eval)

    security_eval = subparsers.add_parser("evaluate-security", help="run the independent Prompt 07 adversarial evaluation")
    security_eval.add_argument("--dataset", type=Path, default=_project_root() / "evaluation/security-v1.json")
    security_eval.add_argument("--split", choices=("development", "final_holdout", "all"), default="final_holdout")
    security_eval.add_argument("--format", choices=("json", "summary"), default="summary")
    _add_retrieval_filters(security_eval)
    _add_sufficiency_options(security_eval)
    _add_vector_options(security_eval)

    qa_eval = subparsers.add_parser("evaluate-qa-holdout", help="run the fixed independent Prompt 11 QA holdout")
    qa_eval.add_argument("--dataset", type=Path, default=_project_root() / "evaluation/qa-holdout-v1.json")
    qa_eval.add_argument("--format", choices=("json", "summary"), default="summary")
    _add_retrieval_filters(qa_eval)
    _add_sufficiency_options(qa_eval)
    _add_vector_options(qa_eval)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "inventory":
        config = InventoryConfig(args.source_root, args.manifest)
        manifest = load_manifest(config.manifest_path)
        records = inventory_documents(config.source_root, manifest, max_bytes=config.max_document_bytes)
        payload = {
            "manifest_version": manifest.version,
            "source_project": manifest.source_project,
            "document_count": len(records),
            "documents": [record.to_mapping() for record in records],
        }
        _print(payload)
        return 1 if any(record.error for record in records) else 0
    if args.command == "ingest":
        try:
            manifest = load_manifest(args.manifest)
            result = ingest_document(
                args.source_root,
                manifest,
                args.document,
                intended_use=args.intended_use,
                chunk_config=ChunkConfig(target_chars=args.target_chars, max_chars=args.max_chars),
            )
            payload = result.to_mapping(include_content=False)
            if args.write_output:
                project_root = _project_root()
                output_path = write_sanitized_snapshot(result, project_root)
                payload["sanitized_output"] = str(output_path.relative_to(project_root))
            _print(payload)
            return 0
        except (SafetyViolation, SanitizationRejected, ValueError, OSError) as exc:
            print(json.dumps({"status": "rejected", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
            return 2
    try:
        if args.command == "model-info":
            provider = _provider(args)
            payload = {"embedding": provider.metadata.to_mapping(), "verified": False}
            if args.verify:
                vector = provider.embed_query("synthetic local embedding verification")
                payload.update(
                    {
                        "verified": True,
                        "actual_dimensions": len(vector),
                        "runtime": provider.runtime_info(),
                    }
                )
            _print(payload)
            return 0
        if args.command == "index":
            manifest = load_manifest(args.manifest)
            result = ingest_document(
                args.source_root,
                manifest,
                args.document,
                intended_use=args.intended_use,
                chunk_config=ChunkConfig(target_chars=args.target_chars, max_chars=args.max_chars),
            )
            provider = _provider(args)
            database = _database(args.database_url)
            migrations = database.migrate()
            report = index_ingestion_result(
                result,
                provider,
                database,
                batch_size=args.batch_size,
                retrieval_policy=SYNTHETIC_EVALUATION_POLICY,
            )
            _print(
                {
                    "status": "indexed",
                    "migrations": migrations,
                    "embedding": provider.metadata.to_mapping(),
                    "indexing": report.to_mapping(),
                }
            )
            return 0
        if args.command == "index-security-fixtures":
            manifest = load_manifest(args.manifest)
            provider = _provider(args)
            database = _database(args.database_url)
            migrations = database.migrate()
            documents = (
                "security-instructions.md", "security-conflicts.md", "security-keyword-poison.md",
                "security-semantic-decoy.md", "security-citation-spoof.md",
            )
            reports = []
            for document in documents:
                result = ingest_document(
                    args.source_root, manifest, document,
                    intended_use="prompt07_security_evaluation",
                    chunk_config=ChunkConfig(target_chars=300, max_chars=600),
                )
                reports.append(index_ingestion_result(
                    result, provider, database, batch_size=args.batch_size,
                    retrieval_policy=SECURITY_EVALUATION_POLICY,
                ).to_mapping())
            _print({
                "status": "indexed", "fixture_count": len(documents), "migrations": migrations,
                "embedding": provider.metadata.to_mapping(), "indexing": reports,
                "retrieval_policy": SECURITY_EVALUATION_POLICY.__dict__,
            })
            return 0
        if args.command == "index-status":
            provider = _provider(args)
            database = _database(args.database_url)
            database.migrate()
            _print(database.status(provider.metadata))
            return 0
        if args.command == "query":
            retriever = _retriever(args)
            response = retriever.search(
                args.query_text,
                mode=RetrievalMode.VECTOR,
                filters=RetrievalFilters(
                    SYNTHETIC_EVALUATION_POLICY.corpus_id,
                    SYNTHETIC_EVALUATION_POLICY.access_policy,
                    "PROMPT-04-SYNTHETIC-VECTOR-FIXTURE",
                    document_classification=SYNTHETIC_EVALUATION_POLICY.document_classification,
                ),
                top_k=args.top_k,
            )
            _print(response.to_mapping())
            return 0
        if args.command == "search":
            response = _retriever(args).search(
                args.query,
                mode=args.mode,
                filters=_retrieval_filters(args),
                top_k=args.top_k,
                candidate_k=args.candidate_k,
                rrf_config=RRFConfig(args.rrf_k, args.keyword_weight, args.vector_weight),
            )
            payload = response.to_mapping()
            _print(payload) if args.format == "json" else _print_search_summary(payload)
            return 0
        if args.command == "evaluate-retrieval":
            dataset = load_evaluation_dataset(args.dataset)
            rrf_config = RRFConfig(args.rrf_k, args.keyword_weight, args.vector_weight)
            command = (
                "threadeye-evidence evaluate-retrieval "
                f"--dataset {args.dataset} --rrf-k {args.rrf_k} "
                f"--keyword-weight {args.keyword_weight} --vector-weight {args.vector_weight}"
            )
            report = evaluate_retrieval(
                dataset,
                _retriever(args),
                _retrieval_filters(args),
                rrf_config=rrf_config,
                command=command,
            )
            _print(report) if args.format == "json" else _print_evaluation_summary(report)
            return 0
        if args.command == "answer-evidence":
            engine = EvidenceAnswerEngine(_retriever(args), sufficiency_config=_sufficiency_config(args))
            response = engine.answer(
                args.question,
                filters=_retrieval_filters(args),
                mode=args.mode,
                top_k=args.top_k,
                candidate_k=args.candidate_k,
                rrf_config=RRFConfig(args.rrf_k, args.keyword_weight, args.vector_weight),
            )
            payload = response.to_mapping()
            _print(payload) if args.format == "json" else _print_answer_summary(payload)
            return 0
        if args.command == "evaluate-answers":
            dataset = load_answer_evaluation_dataset(args.dataset)
            engine = EvidenceAnswerEngine(_retriever(args), sufficiency_config=_sufficiency_config(args))
            command = f"threadeye-evidence evaluate-answers --dataset {args.dataset} --split {args.split}"
            report = evaluate_answers(
                dataset,
                engine,
                _retrieval_filters(args),
                command=command,
                selected_split=args.split,
            )
            _print(report) if args.format == "json" else _print_answer_evaluation_summary(report)
            return 0
        if args.command == "evaluate-security":
            dataset = load_security_dataset(args.dataset)
            engine = EvidenceAnswerEngine(_retriever(args), sufficiency_config=_sufficiency_config(args))
            command = f"threadeye-evidence evaluate-security --dataset {args.dataset} --split {args.split}"
            report = evaluate_security(
                dataset, engine, _retrieval_filters(args), selected_split=args.split, command=command,
            )
            _print(report) if args.format == "json" else _print_security_evaluation_summary(report)
            return 0
        if args.command == "evaluate-qa-holdout":
            historical = (
                _project_root() / "evaluation/retrieval-v1.json",
                _project_root() / "evaluation/answering-v1.json",
                _project_root() / "evaluation/security-v1.json",
            )
            dataset = load_qa_holdout(args.dataset, historical_paths=historical)
            engine = EvidenceAnswerEngine(_retriever(args), sufficiency_config=_sufficiency_config(args))
            command = f"threadeye-evidence evaluate-qa-holdout --dataset {args.dataset}"
            report = evaluate_qa_holdout(dataset, engine, _retrieval_filters(args), command=command)
            _print(report) if args.format == "json" else _print_qa_evaluation_summary(report)
            return 0
    except (
        SafetyViolation,
        SanitizationRejected,
        EmbeddingValidationError,
        ProvenanceValidationError,
        DatabaseSafetyError,
        RetrievalBackendError,
        RetrievalValidationError,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:
        print(json.dumps({"status": "rejected", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    except Exception as exc:
        if exc.__class__.__module__.split(".", 1)[0] == "psycopg":
            print(
                json.dumps({"status": "rejected", "reason": "isolated database operation failed"}, sort_keys=True),
                file=sys.stderr,
            )
            return 2
        raise
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
