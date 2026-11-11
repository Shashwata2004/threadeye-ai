from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from threadeye_evidence.corpus.allowlist import Manifest, ManifestEntry
from threadeye_evidence.corpus.inventory import inventory_documents


def manifest_for(*paths: str) -> Manifest:
    return Manifest(
        1,
        "synthetic",
        tuple(ManifestEntry(path, "Synthetic test", "test_fixture", True, False, "") for path in paths),
    )


class InventoryTests(unittest.TestCase):
    def test_approved_document_is_inventoried_without_contents(self) -> None:
        secret_marker = "document-body-must-not-appear"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text(secret_marker, encoding="utf-8")
            record = inventory_documents(root, manifest_for("README.md"))[0]
            self.assertIsNone(record.error)
            self.assertEqual(record.size_bytes, len(secret_marker.encode()))
            rendered = json.dumps(record.to_mapping())
            self.assertNotIn(secret_marker, rendered)
            self.assertNotIn("content", record.to_mapping())

    def test_missing_document_is_reported_safely(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            record = inventory_documents(Path(directory), manifest_for("MISSING.md"))[0]
            self.assertEqual(record.error, "missing_file")
            self.assertIsNone(record.sha256)

    def test_unexpected_files_are_excluded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("approved", encoding="utf-8")
            (root / "UNEXPECTED.md").write_text("not approved", encoding="utf-8")
            records = inventory_documents(root, manifest_for("README.md"))
            self.assertEqual([record.relative_path for record in records], ["README.md"])

    def test_directory_entry_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs.md").mkdir()
            record = inventory_documents(root, manifest_for("docs.md"))[0]
            self.assertIn("validation_error", record.error or "")

    def test_oversized_document_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("too large", encoding="utf-8")
            record = inventory_documents(root, manifest_for("README.md"), max_bytes=3)[0]
            self.assertIn("exceeds the 3-byte limit", record.error or "")
            self.assertIsNone(record.sha256)


if __name__ == "__main__":
    unittest.main()
