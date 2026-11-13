from __future__ import annotations

import json
import re
from pathlib import Path
import subprocess
import sys
import time
import unittest

from starlette.testclient import TestClient

from threadeye_evidence.ui.app import ASSET_ROOT, UIConfig, build_ui_app
from threadeye_evidence.ui.launcher import _mcp_child_environment, _terminate
from threadeye_evidence.ui.mcp_client import UIGatewayError, UIUnauthorized
from threadeye_evidence.ui.security import SessionStore


ACCESS_CODE = "fictional-local-access-2026"
ORIGIN = "http://127.0.0.1:8770"


class FakeGateway:
    def __init__(self) -> None:
        self.failure: Exception | None = None
        self.invalid_citation = False

    async def overview(self):
        if self.failure:
            raise self.failure
        return {
            "connection": "CONNECTED", "protocol_version": "2025-11-25", "server_version": "0.9.0",
            "authorization_scopes": ["evidence:metadata:read", "evidence:search", "evidence:answer"],
            "capabilities": {"read_only": True, "transport": "streamable-http", "answer_mode": "extractive", "scope": "authorized fictional synthetic evidence only"},
            "sources": {"source_count": 1, "sources": [{"source_relative_path": "technical-evidence.md"}]},
            "security_policy": {"read_only": True, "limits": {"max_top_k": 5}},
        }

    async def search(self, query, mode, top_k):
        if self.failure:
            raise self.failure
        return {
            "status": "ok", "query": query, "mode": mode, "result_count": 1, "backend_status": {},
            "results": [{
                "source_title": "Fabric Receiving", "source_relative_path": "technical-evidence.md",
                "chunk_id": "safe-chunk", "chunk_sha256": "a" * 64, "sanitized_text": "<img src=x onerror=alert(1)>",
                "normalized_start": 0, "normalized_end": 34, "retrieval_methods": ["keyword", "vector"],
                "rrf_score": 0.02, "cosine_similarity": 0.8,
            }],
        }

    async def answer(self, question, mode):
        if self.failure:
            raise self.failure
        if "weather" in question:
            return {
                "question": question, "status": "insufficient_evidence", "answer_mode": "extractive",
                "answer": None, "citations": [], "retrieval_mode": mode,
                "retrieval_metadata": {}, "abstention_reason": "insufficient_relevance",
            }
        citation = {
            "source_relative_path": "technical-evidence.md", "source_sha256": "b" * 64,
            "chunk_id": "safe-chunk", "chunk_sha256": "a" * 64, "heading_hierarchy": ["Fabric Receiving"],
            "normalized_start": 10, "normalized_end": 26, "processing_version": "v1",
            "authorization_reference": "SYNTHETIC", "corpus_version": "v1", "excerpt": "Supplier lot LOT-FX-17.",
        }
        return {
            "question": question, "status": "answered", "answer_mode": "extractive",
            "answer": "wrong" if self.invalid_citation else citation["excerpt"], "citations": [citation],
            "retrieval_mode": mode, "retrieval_metadata": {"citation_validation": {"valid": True}},
            "abstention_reason": None,
        }


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    if not match:
        raise AssertionError("CSRF token missing")
    return match.group(1)


class UIAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.gateway = FakeGateway()
        config = UIConfig(enforce_loopback_client=False)
        self.client = TestClient(build_ui_app(self.gateway, ACCESS_CODE, config=config), base_url=ORIGIN)

    def login(self) -> str:
        page = self.client.get("/")
        response = self.client.post(
            "/session",
            data={"csrf_token": csrf_from(page.text), "access_code": ACCESS_CODE},
            headers={"Origin": ORIGIN},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        session_cookie = response.headers.get("set-cookie", "")
        self.assertIn("HttpOnly", session_cookie)
        self.assertIn("SameSite=strict", session_cookie)
        dashboard = self.client.get("/")
        match = re.search(r'name="csrf-token" content="([^"]+)"', dashboard.text)
        self.assertIsNotNone(match)
        return match.group(1)

    def test_startup_login_and_runtime_connection_status(self) -> None:
        health = self.client.get("/healthz")
        self.assertEqual(health.json(), {"status": "ok", "binding": "loopback", "mcp_checked": False})
        page = self.client.get("/")
        self.assertIn("Local judge access", page.text)
        csrf = self.login()
        dashboard = self.client.get("/")
        self.assertIn("Checking MCP", dashboard.text)
        self.assertNotIn(">Connected<", dashboard.text)
        overview = self.client.get("/api/overview")
        self.assertEqual(overview.json()["state"], "CONNECTED")
        self.assertTrue(overview.json()["data"]["capabilities"]["read_only"])
        self.assertTrue(csrf)

    def test_local_session_is_required(self) -> None:
        response = self.client.get("/api/overview")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["state"], "UNAUTHORIZED")

    def test_host_origin_and_csrf_fail_closed(self) -> None:
        self.assertEqual(self.client.get("/", headers={"Host": "evil.example"}).status_code, 421)
        page = self.client.get("/")
        denied = self.client.post(
            "/session", data={"csrf_token": csrf_from(page.text), "access_code": ACCESS_CODE},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(denied.status_code, 403)
        missing_origin = self.client.post(
            "/session", data={"csrf_token": csrf_from(page.text), "access_code": ACCESS_CODE},
        )
        self.assertEqual(missing_origin.status_code, 403)
        self.login()
        missing = self.client.post(
            "/api/search", json={"query": "x", "mode": "hybrid", "top_k": 1}, headers={"Origin": ORIGIN},
        )
        self.assertEqual(missing.status_code, 403)

    def test_search_validation_limits_and_unexpected_fields(self) -> None:
        csrf = self.login()
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        for body in (
            {"query": "", "mode": "hybrid", "top_k": 1},
            {"query": "x", "mode": "other", "top_k": 1},
            {"query": "x", "mode": "hybrid", "top_k": 6},
            {"query": "x", "mode": "hybrid", "top_k": 1, "corpus": "production"},
            {"query": "x" * 1001, "mode": "hybrid", "top_k": 1},
            {"query": "x\u0001", "mode": "hybrid", "top_k": 1},
        ):
            response = self.client.post("/api/search", json=body, headers=headers)
            self.assertEqual(response.status_code, 400, body)
            self.assertEqual(response.json()["state"], "VALIDATION FAILURE")
        oversized = self.client.post(
            "/api/search",
            content=json.dumps({"query": "x" * 9_000, "mode": "hybrid", "top_k": 1}),
            headers={**headers, "Content-Type": "application/json"},
        )
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(oversized.json()["error"], "request_body_too_large")

    def test_search_and_safe_abstention(self) -> None:
        csrf = self.login()
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        search = self.client.post("/api/search", json={"query": "ROLL-NST-204", "mode": "hybrid", "top_k": 3}, headers=headers)
        self.assertEqual(search.json()["state"], "RESULTS READY")
        self.assertIn("<img", search.json()["data"]["results"][0]["sanitized_text"])
        abstention = self.client.post("/api/answer", json={"question": "What is tomorrow's weather?", "mode": "hybrid"}, headers=headers)
        self.assertEqual(abstention.json()["state"], "ABSTAINED")
        self.assertIsNone(abstention.json()["data"]["answer"])

    def test_valid_citation_and_invalid_citation_fail_closed(self) -> None:
        csrf = self.login()
        headers = {"Origin": ORIGIN, "X-CSRF-Token": csrf}
        body = {"question": "Which supplier lot is recorded?", "mode": "hybrid"}
        answer = self.client.post("/api/answer", json=body, headers=headers)
        self.assertEqual(answer.json()["state"], "ANSWERED")
        self.gateway.invalid_citation = True
        invalid = self.client.post("/api/answer", json=body, headers=headers)
        self.assertEqual(invalid.status_code, 422)
        self.assertEqual(invalid.json()["state"], "VALIDATION FAILURE")
        self.assertNotIn("data", invalid.json())

    def test_backend_and_authorization_failures_are_distinct(self) -> None:
        self.login()
        self.gateway.failure = UIGatewayError("offline")
        unavailable = self.client.get("/api/overview")
        self.assertEqual(unavailable.status_code, 503)
        self.assertEqual(unavailable.json()["state"], "BACKEND UNAVAILABLE")
        self.gateway.failure = UIUnauthorized("scope denied")
        unauthorized = self.client.get("/api/overview")
        self.assertEqual(unauthorized.status_code, 403)
        self.assertEqual(unauthorized.json()["state"], "UNAUTHORIZED")

    def test_xss_safe_renderer_and_no_browser_secret_storage(self) -> None:
        script = (ASSET_ROOT / "app.js").read_text(encoding="utf-8")
        self.assertIn("textContent", script)
        self.assertNotIn("innerHTML", script)
        self.assertNotIn("localStorage", script)
        self.assertNotIn("sessionStorage", script)
        self.assertNotIn('"Authorization":', script)
        self.assertNotIn("Bearer", script)

    def test_security_headers_no_wildcard_cors_and_read_only_routes(self) -> None:
        response = self.client.get("/")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertEqual(response.headers["x-frame-options"], "DENY")
        self.assertEqual(response.headers["referrer-policy"], "same-origin")
        self.assertNotEqual(response.headers.get("access-control-allow-origin"), "*")
        self.assertEqual(self.client.put("/api/search", headers={"Origin": ORIGIN}).status_code, 405)


class SessionAndShutdownTests(unittest.TestCase):
    def test_mcp_child_environment_excludes_ui_and_unrelated_credentials(self) -> None:
        required = {
            "THREADEYE_EVIDENCE_MCP_CONFIG": "/safe/config.json",
            "THREADEYE_EVIDENCE_MCP_DATABASE_URL": "postgresql://read-only:fixture@127.0.0.1:55432/threadeye_evidence",
            "THREADEYE_EVIDENCE_MODEL_CACHE": "/safe/cache",
            "PYTHONPATH": "/safe/src",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        child = _mcp_child_environment(required, Path("/safe/http.json"), Path("/safe/public.pem"))
        self.assertEqual(child["THREADEYE_EVIDENCE_MCP_DATABASE_URL"], required["THREADEYE_EVIDENCE_MCP_DATABASE_URL"])
        self.assertNotIn("THREADEYE_EVIDENCE_UI_ACCESS_CODE", child)
        self.assertNotIn("THREADEYE_EVIDENCE_ADMIN_DATABASE_URL", child)
        self.assertNotIn("SUPABASE_URL", child)

    def test_session_expiry_and_bounded_store(self) -> None:
        now = [100.0]
        store = SessionStore(ACCESS_CODE, idle_seconds=10, absolute_seconds=20, max_sessions=2, clock=lambda: now[0])
        preauth, csrf = store.new_preauth()
        session_id, _ = store.login(preauth, csrf, ACCESS_CODE, "loopback")
        self.assertIsNotNone(store.get(session_id))
        now[0] += 11
        self.assertIsNone(store.get(session_id))
        self.assertEqual(store.active_sessions, 0)

    def test_clean_subprocess_shutdown(self) -> None:
        process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        _terminate(process)
        self.assertIsNotNone(process.poll())


if __name__ == "__main__":
    unittest.main()
