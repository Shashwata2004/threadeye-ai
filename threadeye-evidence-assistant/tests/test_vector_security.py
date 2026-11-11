from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

from threadeye_evidence.corpus.allowlist import load_manifest


ROOT = Path(__file__).resolve().parents[1]


class VectorSecurityTests(unittest.TestCase):
    def test_real_documents_remain_unapproved(self) -> None:
        manifest = load_manifest(ROOT / "knowledge" / "manifest.json")
        self.assertEqual(len(manifest.documents), 6)
        self.assertTrue(all(not entry.future_ingestion_approved for entry in manifest.documents))

    def test_database_port_is_loopback_only(self) -> None:
        compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
        self.assertIn('"127.0.0.1:${EVIDENCE_DB_PORT:-55432}:5432"', compose)
        self.assertNotIn('"${EVIDENCE_DB_PORT:-55432}:5432"', compose)
        self.assertIn("threadeye-evidence-assistant-network", compose)

    def test_model_caches_and_secrets_are_not_tracked(self) -> None:
        tracked = subprocess.run(
            ["git", "ls-files", "--", "threadeye-evidence-assistant"],
            cwd=ROOT.parent,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        self.assertNotIn(".env.db\n", tracked)
        self.assertNotIn("build/model-cache", tracked)
        self.assertNotIn(".onnx", tracked)
