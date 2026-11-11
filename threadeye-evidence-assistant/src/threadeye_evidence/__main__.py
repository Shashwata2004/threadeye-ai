"""Command-line entry point for the read-only inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from threadeye_evidence.config import InventoryConfig
from threadeye_evidence.corpus.allowlist import load_manifest
from threadeye_evidence.corpus.inventory import inventory_documents


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
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
