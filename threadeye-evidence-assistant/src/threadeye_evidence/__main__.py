"""Command-line entry point for inventory, ingestion, embeddings, and vector verification."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Sequence

from threadeye_evidence.config import InventoryConfig
from threadeye_evidence.corpus.allowlist import load_manifest
from threadeye_evidence.corpus.chunking import ChunkConfig
from threadeye_evidence.corpus.ingestion import ingest_document
from threadeye_evidence.corpus.inventory import inventory_documents
from threadeye_evidence.corpus.output import write_sanitized_snapshot
from threadeye_evidence.corpus.safety import SafetyViolation
from threadeye_evidence.corpus.sanitization import SanitizationRejected
from threadeye_evidence.vector.database import DatabaseSafetyError, DatabaseSettings, EvidenceDatabase
from threadeye_evidence.vector.embeddings import EmbeddingValidationError, FastEmbedProvider
from threadeye_evidence.vector.indexing import default_migrations_dir, index_ingestion_result, vector_query
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ThreadEye metadata-only evidence inventory")
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

    status = subparsers.add_parser("index-status", help="show isolated pgvector index status")
    _add_vector_options(status)

    query = subparsers.add_parser("query", help="run exact cosine search over sanitized synthetic chunks")
    query.add_argument("query_text", help="non-empty synthetic verification query")
    query.add_argument("--top-k", type=int, default=5)
    _add_vector_options(query)
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
                project_root = Path(__file__).resolve().parents[2]
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
            report = index_ingestion_result(result, provider, database, batch_size=args.batch_size)
            _print(
                {
                    "status": "indexed",
                    "migrations": migrations,
                    "embedding": provider.metadata.to_mapping(),
                    "indexing": report.to_mapping(),
                }
            )
            return 0
        if args.command == "index-status":
            provider = _provider(args)
            database = _database(args.database_url)
            database.migrate()
            _print(database.status(provider.metadata))
            return 0
        if args.command == "query":
            provider = _provider(args)
            database = _database(args.database_url)
            database.migrate()
            results = vector_query(args.query_text, provider, database, top_k=args.top_k)
            _print(
                {
                    "query": args.query_text,
                    "top_k": args.top_k,
                    "result_count": len(results),
                    "embedding": provider.metadata.to_mapping(),
                    "results": [result.to_mapping() for result in results],
                }
            )
            return 0
    except (
        SafetyViolation,
        SanitizationRejected,
        EmbeddingValidationError,
        ProvenanceValidationError,
        DatabaseSafetyError,
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
