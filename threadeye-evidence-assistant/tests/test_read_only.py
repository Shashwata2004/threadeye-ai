from __future__ import annotations

import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from threadeye_evidence.corpus.allowlist import Manifest, ManifestEntry
from threadeye_evidence.corpus.hashing import sha256_file
from threadeye_evidence.corpus.inventory import inventory_documents


class ReadOnlyTests(unittest.TestCase):
    def test_inventory_does_not_modify_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "README.md"
            source.write_text("stable synthetic fixture", encoding="utf-8")
            before_stat = source.stat()
            before_hash = sha256_file(source)
            manifest = Manifest(
                1,
                "synthetic",
                (ManifestEntry("README.md", "Test", "test_fixture", True, False, ""),),
            )
            record = inventory_documents(root, manifest)[0]
            after_stat = source.stat()
            self.assertIsNone(record.error)
            self.assertEqual(before_hash, sha256_file(source))
            self.assertEqual(before_stat.st_size, after_stat.st_size)
            self.assertEqual(before_stat.st_mtime_ns, after_stat.st_mtime_ns)
            self.assertEqual(before_stat.st_mode, after_stat.st_mode)
            self.assertEqual(sorted(path.name for path in root.iterdir()), ["README.md"])

    def test_inventory_requires_no_network_or_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("offline fixture", encoding="utf-8")
            manifest = Manifest(
                1,
                "synthetic",
                (ManifestEntry("README.md", "Test", "test_fixture", True, False, ""),),
            )
            with patch.object(socket, "socket", side_effect=AssertionError("network access attempted")):
                record = inventory_documents(root, manifest)[0]
            self.assertIsNone(record.error)


if __name__ == "__main__":
    unittest.main()
