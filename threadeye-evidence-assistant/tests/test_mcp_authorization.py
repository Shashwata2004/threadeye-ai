from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from threadeye_evidence.mcp.authorization import AuthorizationConfigurationError, TrustedAuthorizationContext


ROOT = Path(__file__).resolve().parents[1]


class MCPAuthorizationTests(unittest.TestCase):
    def test_missing_trusted_context_fails_closed(self) -> None:
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(AuthorizationConfigurationError):
            TrustedAuthorizationContext.from_environment()

    def test_tracked_operator_context_is_strict_and_fixed(self) -> None:
        context = TrustedAuthorizationContext.load(ROOT / "config/mcp-synthetic.json")
        filters = context.filters()
        self.assertEqual(filters.corpus_id, "threadeye-synthetic-evidence-v1")
        self.assertEqual(filters.access_policy, "prompt05-test-only")
        self.assertEqual(filters.source_relative_path, "technical-evidence.md")
        self.assertEqual(context.max_top_k, 5)

    def test_symlink_broad_write_and_unknown_fields_are_rejected(self) -> None:
        original = json.loads((ROOT / "config/mcp-synthetic.json").read_text(encoding="utf-8"))
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "config.json"
            target.write_text(json.dumps(original), encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaises(AuthorizationConfigurationError):
                TrustedAuthorizationContext.load(link)
            target.chmod(0o666)
            with self.assertRaises(AuthorizationConfigurationError):
                TrustedAuthorizationContext.load(target)
            target.chmod(0o600)
            original["client_corpus_override"] = True
            target.write_text(json.dumps(original), encoding="utf-8")
            with self.assertRaises(AuthorizationConfigurationError):
                TrustedAuthorizationContext.load(target)


if __name__ == "__main__":
    unittest.main()
