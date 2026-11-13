from __future__ import annotations

import hashlib
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from threadeye_evidence.corpus.allowlist import Manifest, ManifestEntry, TeamAuthorization
from threadeye_evidence.corpus.chunking import ChunkConfig
from threadeye_evidence.corpus.ingestion import IngestionError, ingest_document
from threadeye_evidence.corpus.output import write_sanitized_snapshot
from threadeye_evidence.corpus.safety import SafetyViolation


RAW_SECRET = "SYNTHETIC_SECRET_VALUE_123456"


def approved_manifest(content: bytes, *, expected_hash: str | None = None) -> Manifest:
    authorization = TeamAuthorization("TEST-AUTH", "synthetic_test", "test-suite", "synthetic_only")
    entry = ManifestEntry(
        "demo.md",
        "Synthetic",
        "test_fixture",
        True,
        True,
        "",
        authorization,
        expected_hash if expected_hash is not None else hashlib.sha256(content).hexdigest(),
    )
    return Manifest(1, "synthetic", (entry,))


class IngestionTests(unittest.TestCase):
    def test_full_pipeline_redacts_normalizes_chunks_and_tracks_provenance(self) -> None:
        source = f"# Demo\r\n\r\napi_key = {RAW_SECRET}\r\n\r\n## Child\r\nEvidence paragraph.\r\n"
        content = source.encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.md").write_bytes(content)
            result = ingest_document(
                root,
                approved_manifest(content),
                "demo.md",
                intended_use="synthetic_test",
                chunk_config=ChunkConfig(target_chars=100, max_chars=180),
            )
        self.assertNotIn(RAW_SECRET, result.normalized_text)
        self.assertEqual(result.sanitization_status, "redacted")
        self.assertEqual(result.source_sha256, hashlib.sha256(content).hexdigest())
        self.assertEqual(result.normalized_sha256, hashlib.sha256(result.normalized_text.encode()).hexdigest())
        self.assertEqual("".join(chunk.content for chunk in result.chunks), result.normalized_text)
        self.assertTrue(all(chunk.source_sha256 == result.source_sha256 for chunk in result.chunks))

    def test_hash_mismatch_is_rejected_without_content_disclosure(self) -> None:
        content = b"# Demo\n\nSafe text.\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.md").write_bytes(content)
            with self.assertRaises(IngestionError) as raised:
                ingest_document(
                    root,
                    approved_manifest(content, expected_hash="0" * 64),
                    "demo.md",
                    intended_use="synthetic_test",
                )
        self.assertNotIn("Safe text", str(raised.exception))

    def test_safe_statistics_and_snapshot_never_contain_raw_secret(self) -> None:
        content = f"# Demo\n\npassword = {RAW_SECRET}\n".encode()
        with tempfile.TemporaryDirectory() as source_directory, tempfile.TemporaryDirectory() as project_directory:
            source_root = Path(source_directory)
            (source_root / "demo.md").write_bytes(content)
            result = ingest_document(
                source_root,
                approved_manifest(content),
                "demo.md",
                intended_use="synthetic_test",
            )
            safe_stats = json.dumps(result.to_mapping(include_content=False))
            destination = write_sanitized_snapshot(result, Path(project_directory))
            persisted = destination.read_text(encoding="utf-8")
        self.assertNotIn(RAW_SECRET, safe_stats)
        self.assertNotIn(RAW_SECRET, persisted)
        self.assertIn("[REDACTED_CREDENTIAL]", persisted)

    def test_ingestion_needs_no_network_or_database(self) -> None:
        content = b"# Offline\n\nSynthetic content.\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.md").write_bytes(content)
            with patch.object(socket, "socket", side_effect=AssertionError("network access attempted")):
                result = ingest_document(
                    root,
                    approved_manifest(content),
                    "demo.md",
                    intended_use="synthetic_test",
                )
        self.assertEqual(result.sanitization_status, "clean")

    def test_ingestion_is_deterministic(self) -> None:
        content = b"# Repeatable\n\nSynthetic paragraph.\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.md").write_bytes(content)
            manifest = approved_manifest(content)
            first = ingest_document(root, manifest, "demo.md", intended_use="synthetic_test")
            second = ingest_document(root, manifest, "demo.md", intended_use="synthetic_test")
        self.assertEqual(first, second)

    def test_ingestion_enforces_size_limit(self) -> None:
        content = b"# Oversized\n\nSynthetic paragraph.\n"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "demo.md").write_bytes(content)
            with self.assertRaises(SafetyViolation):
                ingest_document(
                    root,
                    approved_manifest(content),
                    "demo.md",
                    intended_use="synthetic_test",
                    max_bytes=8,
                )


if __name__ == "__main__":
    unittest.main()
