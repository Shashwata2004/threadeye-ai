from __future__ import annotations

import re
import unittest
from pathlib import Path

from threadeye_evidence import __version__


ROOT = Path(__file__).resolve().parents[1]


class ReleaseMetadataTests(unittest.TestCase):
    def test_package_runtime_version_matches_project_metadata(self) -> None:
        text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        match = re.search(r'^version = "([^"]+)"$', text, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(__version__, match.group(1))


if __name__ == "__main__":
    unittest.main()
