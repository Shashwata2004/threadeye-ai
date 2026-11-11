"""Command-line entry point for the read-only inventory."""

from __future__ import annotations

import argparse
import json
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
        print(json.dumps(payload, indent=2, sort_keys=True))
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
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        except (SafetyViolation, SanitizationRejected, ValueError, OSError) as exc:
            print(json.dumps({"status": "rejected", "reason": str(exc)}, sort_keys=True), file=sys.stderr)
            return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
