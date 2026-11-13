from __future__ import annotations

import anyio
import os
import unittest

from threadeye_evidence.mcp.verify_http import verify_http


RUN = (
    os.environ.get("THREADEYE_RUN_DB_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_MODEL_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_MCP_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_HTTP_TESTS") == "1"
    and os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL")
    and os.environ.get("THREADEYE_EVIDENCE_MCP_CONFIG")
    and os.environ.get("THREADEYE_EVIDENCE_MODEL_CACHE")
)


@unittest.skipUnless(RUN, "real authenticated MCP HTTP integration not requested")
class MCPHTTPIntegrationTests(unittest.TestCase):
    def test_two_official_clients_auth_security_rate_limit_and_shutdown(self) -> None:
        report = anyio.run(verify_http)
        self.assertEqual(report["client_a"]["protocol_version"], "2025-11-25")
        self.assertTrue(report["client_a"]["tools_exact"])
        self.assertTrue(report["client_a"]["resources_exact"])
        self.assertEqual(report["client_a"]["search"]["sources"], ["technical-evidence.md"])
        self.assertTrue(report["client_a"]["search"]["provenance"])
        self.assertTrue(report["client_a"]["answer"]["citation_valid"])
        self.assertTrue(report["client_a"]["unsupported"]["answer_is_null"])
        for outcome in report["client_a"]["negative"].values():
            self.assertTrue(outcome["rejected"])
            self.assertFalse(outcome["evidence_leaked"])
        self.assertTrue(report["client_b"]["metadata_read"])
        self.assertTrue(report["client_b"]["search"]["denied"])
        self.assertTrue(report["client_b"]["answer"]["denied"])
        self.assertFalse(report["client_b"]["client_a_context_inherited"])
        negatives = report["authentication_and_http_negatives"]
        for name in (
            "missing_token", "invalid_header", "empty_token", "expired", "invalid_signature",
            "unknown_key", "unsupported_algorithm", "wrong_issuer", "wrong_audience", "future_nbf",
            "missing_subject", "missing_scope", "unsupported_scope", "malformed_claims", "wrong_token_type",
            "unauthorized_principal", "malformed", "unsigned",
        ):
            self.assertEqual(negatives[name], 401, name)
        self.assertEqual(negatives["invalid_host"], 421)
        self.assertEqual(negatives["invalid_origin"], 403)
        self.assertEqual(negatives["oversized_body"], 413)
        self.assertEqual(negatives["duplicate_authorization"], 400)
        self.assertTrue(negatives["challenge_has_metadata"])
        self.assertTrue(negatives["cors_wildcard_absent"])
        self.assertTrue(negatives["metadata_cors_wildcard_absent"])
        self.assertEqual(report["rate_limit"]["limited_status"], 429)
        self.assertEqual(report["rate_limit"]["recovered_status"], 200)
        self.assertTrue(all(value for key, value in report["audit_log"].items() if key != "tamper_proof_claimed"))
        self.assertFalse(report["audit_log"]["tamper_proof_claimed"])
        self.assertIn("second process", report["shutdown_restart"])


if __name__ == "__main__":
    unittest.main()
