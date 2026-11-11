from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from threadeye_evidence.corpus.normalization import normalize_markdown


class NormalizationTests(unittest.TestCase):
    def test_normalization_is_repeatable_and_preserves_headings(self) -> None:
        source = "\r\n# Heading  \r\n\r\n\r\nParagraph.   \r\n\r\n## Child\r\n- item  \r\n"
        first = normalize_markdown(source)
        self.assertEqual(first, normalize_markdown(source))
        self.assertIn("# Heading\n", first)
        self.assertIn("## Child\n", first)
        self.assertNotIn("\r", first)
        self.assertNotIn("\n\n\n", first)

    def test_fenced_code_is_preserved_as_text(self) -> None:
        source = "# Code\n\n```bash\necho 'hello'\n\n# not a heading\n```\n"
        normalized = normalize_markdown(source)
        self.assertIn("```bash\necho 'hello'\n\n# not a heading\n```", normalized)

    def test_document_instructions_are_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory, "must-not-exist")
            source = f"```bash\ntouch {marker}\n```\n"
            normalized = normalize_markdown(source)
            self.assertIn("touch", normalized)
            self.assertFalse(marker.exists())


if __name__ == "__main__":
    unittest.main()
