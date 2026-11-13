from __future__ import annotations

import anyio
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import httpx2
import logging
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from pathlib import Path
from types import SimpleNamespace
import unittest

from threadeye_evidence.mcp.http_authorization import (
    METADATA_SCOPE,
    SEARCH_SCOPE,
    EdDSAAccessTokenVerifier,
    HTTPAuthorizationConfig,
)
from threadeye_evidence.mcp.http_server import build_http_app
from threadeye_evidence.mcp.verify_http import issue_test_token


ROOT = Path(__file__).resolve().parents[1]


class FakeService:
    def __init__(self) -> None:
        self.authorization = SimpleNamespace(max_concurrency=1, tool_timeout_seconds=1.0)
    def search(self, query, mode, top_k): return {"status": "ok", "results": []}
    def answer(self, question, mode): return {"status": "insufficient_evidence", "citations": []}
    def list_sources(self): return {"source_count": 0, "sources": []}
    def capabilities(self): return {"read_only": True}
    def security_policy(self): return {"read_only": True}


class FailingService(FakeService):
    def search(self, query, mode, top_k):
        raise RuntimeError("synthetic backend outage; database-password-must-not-leak")


async def fault_injection_report(app, config, token):
    transport_backend = httpx2.ASGITransport(app=app, client=("127.0.0.1", 54321))
    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=transport_backend,
            headers={"Authorization": f"Bearer {token}"},
        ) as http_client:
            transport = streamable_http_client(
                config.resource_url, http_client=http_client, terminate_on_close=False
            )
            async with Client(transport, mode="legacy") as client:
                result = await client.call_tool("search_evidence", {"query": "synthetic evidence"})
    return {"is_error": bool(result.is_error), "rendered": str(result)}


class MCPHTTPServerTests(unittest.TestCase):
    def test_app_uses_sdk_http_auth_metadata_and_security_middleware(self) -> None:
        config = HTTPAuthorizationConfig.load(ROOT / "config/mcp-http.json")
        private_key = Ed25519PrivateKey.generate()
        verifier = EdDSAAccessTokenVerifier(config, private_key.public_key())
        logger = logging.getLogger(f"threadeye-http-server-test-{id(self)}")
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        app = build_http_app(FakeService(), config, verifier, logger=logger)
        paths = {getattr(route, "path", None) for route in app.router.routes}
        self.assertIn("/mcp", paths)
        self.assertIn("/.well-known/oauth-protected-resource/mcp", paths)
        middleware = [item.cls.__name__ for item in app.user_middleware]
        self.assertEqual(middleware[0], "PreAuthHTTPSecurityMiddleware")
        self.assertIn("AuthenticationMiddleware", middleware)
        self.assertIn("AuthContextMiddleware", middleware)
        self.assertEqual(middleware[-1], "PostAuthHTTPControlMiddleware")
        self.assertTrue(app.state.threadeye_server._lowlevel_server._session_manager.stateless)
        self.assertEqual(app.state.threadeye_http_config.host, "127.0.0.1")

    def test_shared_http_tool_path_fails_safely_on_backend_outage(self) -> None:
        config = HTTPAuthorizationConfig.load(ROOT / "config/mcp-http.json")
        private_key = Ed25519PrivateKey.generate()
        verifier = EdDSAAccessTokenVerifier(config, private_key.public_key())
        logger = logging.getLogger(f"threadeye-http-fault-test-{id(self)}")
        logger.handlers.clear()
        logger.addHandler(logging.NullHandler())
        logger.propagate = False
        app = build_http_app(FailingService(), config, verifier, logger=logger)
        token = issue_test_token(
            private_key,
            config,
            "threadeye-evidence-client",
            [METADATA_SCOPE, SEARCH_SCOPE],
        )
        report = anyio.run(fault_injection_report, app, config, token)
        self.assertTrue(report["is_error"])
        self.assertNotIn("database-password", report["rendered"])


if __name__ == "__main__":
    unittest.main()
