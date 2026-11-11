from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from threadeye_evidence.corpus.allowlist import (
    IngestionAuthorizationError,
    Manifest,
    ManifestEntry,
    TeamAuthorization,
    load_manifest,
)
from threadeye_evidence.corpus.ingestion import ingest_document


def entry(*, inventory: bool = True, ingestion: bool = False, authorization: bool = False) -> ManifestEntry:
    auth = TeamAuthorization("TEST-AUTH", "synthetic_test", "test-suite", "synthetic_only") if authorization else None
    return ManifestEntry(
        "demo.md",
        "Synthetic",
        "test_fixture",
        inventory,
        ingestion,
        "",
        auth,
        None,
    )


class AuthorizationTests(unittest.TestCase):
    def test_unapproved_document_is_rejected(self) -> None:
        manifest = Manifest(1, "test", (entry(inventory=False),))
        with self.assertRaises(IngestionAuthorizationError):
            manifest.require_ingestion_authorized("demo.md", "synthetic_test")

    def test_inventory_approval_does_not_imply_ingestion_approval(self) -> None:
        manifest = Manifest(1, "test", (entry(inventory=True, ingestion=False),))
        with self.assertRaises(IngestionAuthorizationError):
            manifest.require_ingestion_authorized("demo.md", "synthetic_test")

    def test_missing_team_authorization_is_rejected(self) -> None:
        manifest = Manifest(1, "test", (entry(inventory=True, ingestion=True),))
        with self.assertRaisesRegex(IngestionAuthorizationError, "no documented team authorization"):
            manifest.require_ingestion_authorized("demo.md", "synthetic_test")

    def test_authorization_must_match_intended_use(self) -> None:
        manifest = Manifest(1, "test", (entry(inventory=True, ingestion=True, authorization=True),))
        with self.assertRaisesRegex(IngestionAuthorizationError, "does not cover"):
            manifest.require_ingestion_authorized("demo.md", "different_use")

    def test_real_manifest_documents_remain_blocked(self) -> None:
        manifest = load_manifest(Path("knowledge/manifest.json"))
        self.assertTrue(all(not document.future_ingestion_approved for document in manifest.documents))
        with patch.object(Path, "read_bytes", side_effect=AssertionError("real document content was read")):
            with self.assertRaises(IngestionAuthorizationError):
                ingest_document(Path(".."), manifest, "README.md", intended_use="prompt03_synthetic_demo")


if __name__ == "__main__":
    unittest.main()
