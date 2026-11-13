"""Synthetic-only helpers shared by Prompt 04 tests."""

from __future__ import annotations

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from threadeye_evidence.corpus.allowlist import Manifest, ManifestEntry, TeamAuthorization
from threadeye_evidence.corpus.chunking import ChunkConfig
from threadeye_evidence.corpus.ingestion import IngestionResult, ingest_document


def synthetic_result(
    content: str | None = None,
    *,
    relative_path: str = "fixture.md",
    intended_use: str = "prompt04_test",
) -> IngestionResult:
    value = content or (
        "# Fictional Evidence\n\n"
        "## Receiving\n\nA synthetic fabric roll arrives in a quarantine lane for receiving review.\n\n"
        "## Supervisor Review\n\nA fictional supervisor reviews the sanitized classification evidence.\n"
    )
    encoded = value.encode("utf-8")
    authorization = TeamAuthorization("PROMPT-04-TEST", intended_use, "test-suite", "synthetic_only")
    entry = ManifestEntry(
        relative_path,
        "synthetic vector test",
        "synthetic_test_fixture",
        True,
        True,
        "fictional",
        authorization,
        hashlib.sha256(encoded).hexdigest(),
    )
    manifest = Manifest(1, "synthetic-tests", (entry,))
    with TemporaryDirectory() as directory:
        root = Path(directory)
        (root / relative_path).write_bytes(encoded)
        return ingest_document(
            root,
            manifest,
            relative_path,
            intended_use=intended_use,
            chunk_config=ChunkConfig(target_chars=100, max_chars=180),
        )
