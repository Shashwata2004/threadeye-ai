from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from threadeye_evidence.corpus.allowlist import Manifest, ManifestEntry
from threadeye_evidence.corpus.safety import SafetyViolation, resolve_source_file, validate_relative_path


class AllowlistTests(unittest.TestCase):
    def setUp(self) -> None:
        self.entry = ManifestEntry("README.md", "Test", "documentation", True, False, "")
        self.manifest = Manifest(1, "test", (self.entry,))

    def test_approved_file_is_accepted(self) -> None:
        self.assertEqual(self.manifest.require_approved("README.md"), self.entry)

    def test_unapproved_file_is_rejected(self) -> None:
        with self.assertRaises(SafetyViolation):
            self.manifest.require_approved("OTHER.md")

    def test_path_traversal_is_rejected(self) -> None:
        with self.assertRaises(SafetyViolation):
            validate_relative_path("../README.md")

    def test_absolute_path_is_rejected(self) -> None:
        with self.assertRaises(SafetyViolation):
            validate_relative_path("/tmp/README.md")

    def test_secret_like_paths_are_rejected(self) -> None:
        for candidate in (".env", "secrets.json", "private.key", "database.sql", ".config/settings.md"):
            with self.subTest(candidate=candidate), self.assertRaises(SafetyViolation):
                validate_relative_path(candidate)

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks are unavailable")
    def test_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as root_dir, tempfile.TemporaryDirectory() as outside_dir:
            root = Path(root_dir)
            outside = Path(outside_dir, "outside.md")
            outside.write_text("outside", encoding="utf-8")
            (root / "README.md").symlink_to(outside)
            with self.assertRaises(SafetyViolation):
                resolve_source_file(root, "README.md")

    def test_manifest_defaults_future_ingestion_to_false(self) -> None:
        entry = ManifestEntry.from_mapping(
            {
                "path": "README.md",
                "purpose": "Test",
                "source_classification": "documentation",
                "inventory_approved": True,
            }
        )
        self.assertFalse(entry.future_ingestion_approved)


if __name__ == "__main__":
    unittest.main()
