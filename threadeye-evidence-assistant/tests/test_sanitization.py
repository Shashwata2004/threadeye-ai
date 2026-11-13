from __future__ import annotations

import unittest

from threadeye_evidence.corpus.sanitization import SanitizationRejected, sanitize_markdown


class SanitizationTests(unittest.TestCase):
    def test_supported_sensitive_values_are_redacted(self) -> None:
        raw_values = (
            "inspector@example.test",
            "DEMO_SECRET_123456789",
            "postgresql://user:password@127.0.0.1:5432/db",
            "http://factory.internal:8080/private",
            "FACTORY-42",
        )
        source = "\n".join(
            (
                f"email: {raw_values[0]}",
                f"api_key = {raw_values[1]}",
                f"db = {raw_values[2]}",
                f"endpoint = {raw_values[3]}",
                f"factory_id = {raw_values[4]}",
            )
        )
        result = sanitize_markdown(source)
        for raw in raw_values:
            self.assertNotIn(raw, result.text)
        self.assertEqual(result.status, "redacted")
        self.assertGreaterEqual(len(result.findings), 5)

    def test_private_key_material_fails_closed_without_echoing_content(self) -> None:
        private_marker = "-----BEGIN PRIVATE KEY-----"
        with self.assertRaises(SanitizationRejected) as raised:
            sanitize_markdown(f"{private_marker}\nVERY_PRIVATE_BYTES")
        self.assertNotIn("VERY_PRIVATE_BYTES", str(raised.exception))
        self.assertNotIn(private_marker, str(raised.exception))

    def test_clean_content_is_unchanged(self) -> None:
        source = "# Public heading\n\nA general quality statement.\n"
        result = sanitize_markdown(source)
        self.assertEqual(result.text, source)
        self.assertEqual(result.status, "clean")
        self.assertEqual(result.findings, ())


if __name__ == "__main__":
    unittest.main()
