from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from threadeye_evidence.corpus.hashing import sha256_file


class HashingTests(unittest.TestCase):
    def test_sha256_is_accurate_and_deterministic(self) -> None:
        content = b"ThreadEye synthetic test document\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "document.md")
            path.write_bytes(content)
            expected = hashlib.sha256(content).hexdigest()
            self.assertEqual(sha256_file(path), expected)
            self.assertEqual(sha256_file(path), expected)

    def test_modified_content_changes_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory, "document.md")
            path.write_text("before", encoding="utf-8")
            before = sha256_file(path)
            path.write_text("after", encoding="utf-8")
            self.assertNotEqual(sha256_file(path), before)


if __name__ == "__main__":
    unittest.main()
