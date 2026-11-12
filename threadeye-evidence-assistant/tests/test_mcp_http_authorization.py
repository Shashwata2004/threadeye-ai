from __future__ import annotations

import anyio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import json
from pathlib import Path
import tempfile
import time
import unittest

from threadeye_evidence.mcp.authorization import AuthorizationConfigurationError
from threadeye_evidence.mcp.http_authorization import (
    ANSWER_SCOPE,
    METADATA_SCOPE,
    SEARCH_SCOPE,
    EdDSAAccessTokenVerifier,
    HTTPAuthorizationConfig,
)
from threadeye_evidence.mcp.verify_http import issue_test_token


ROOT = Path(__file__).resolve().parents[1]


class HTTPAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = HTTPAuthorizationConfig.load(ROOT / "config/mcp-http.json")
        self.private_key = Ed25519PrivateKey.generate()
        self.verifier = EdDSAAccessTokenVerifier(self.config, self.private_key.public_key())

    def verify(self, token: str):
        return anyio.run(self.verifier.verify_token, token)

    def test_valid_asymmetric_access_tokens_preserve_least_privilege(self) -> None:
        full = issue_test_token(
            self.private_key,
            self.config,
            "threadeye-evidence-client",
            [METADATA_SCOPE, SEARCH_SCOPE, ANSWER_SCOPE],
        )
        verified = self.verify(full)
        self.assertEqual(verified.subject, "threadeye-evidence-client")
        self.assertEqual(verified.resource, self.config.resource_url)
        self.assertEqual(set(verified.scopes), {METADATA_SCOPE, SEARCH_SCOPE, ANSWER_SCOPE})
        metadata = issue_test_token(
            self.private_key,
            self.config,
            "threadeye-metadata-client",
            [METADATA_SCOPE],
        )
        self.assertEqual(self.verify(metadata).scopes, [METADATA_SCOPE])

    def test_claim_signature_algorithm_key_and_principal_failures_deny(self) -> None:
        now = int(time.time())
        other_key = Ed25519PrivateKey.generate()
        variants = (
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], now=now - 500),
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], signing_key=other_key),
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], header_overrides={"kid": "unknown"}),
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"iss": "https://wrong.example"}),
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"aud": "http://127.0.0.1:1/mcp"}),
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"nbf": now + 60}),
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], omit={"sub"}),
            issue_test_token(self.private_key, self.config, "threadeye-evidence-client", [METADATA_SCOPE], omit={"scope"}),
            issue_test_token(self.private_key, self.config, "unknown-client", [METADATA_SCOPE]),
            issue_test_token(self.private_key, self.config, "threadeye-metadata-client", [METADATA_SCOPE, SEARCH_SCOPE]),
            "not.a.jwt",
            "x" * (self.config.max_token_chars + 1),
        )
        for token in variants:
            with self.subTest(token_length=len(token)):
                self.assertIsNone(self.verify(token))

    def test_http_config_is_strict_operator_owned_and_loopback_only(self) -> None:
        raw = json.loads((ROOT / "config/mcp-http.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            path = directory / "config.json"

            def write(value) -> None:
                path.write_text(json.dumps(value), encoding="utf-8")
                path.chmod(0o600)

            for mutate in (
                lambda item: item.update(host="0.0.0.0"),
                lambda item: item.update(resource_url="http://127.0.0.1:1/mcp"),
                lambda item: item.update(allowed_algorithm="HS256"),
                lambda item: item.update(extra="not-allowed"),
            ):
                candidate = dict(raw)
                mutate(candidate)
                write(candidate)
                with self.assertRaises(AuthorizationConfigurationError):
                    HTTPAuthorizationConfig.load(path)
            write(raw)
            path.chmod(0o666)
            with self.assertRaises(AuthorizationConfigurationError):
                HTTPAuthorizationConfig.load(path)
            path.chmod(0o600)
            link = directory / "link.json"
            link.symlink_to(path)
            with self.assertRaises(AuthorizationConfigurationError):
                HTTPAuthorizationConfig.load(link)


if __name__ == "__main__":
    unittest.main()
