from __future__ import annotations

import anyio
from io import StringIO
import json
import logging
from pathlib import Path
import unittest

from threadeye_evidence.mcp.http_authorization import HTTPAuthorizationConfig
from threadeye_evidence.mcp.http_security import (
    InMemoryRateLimiter,
    PostAuthHTTPControlMiddleware,
    PreAuthHTTPSecurityMiddleware,
    audit_event,
)


ROOT = Path(__file__).resolve().parents[1]


class Clock:
    def __init__(self) -> None: self.value = 0.0
    def __call__(self) -> float: return self.value


def logger_and_stream():
    stream = StringIO()
    logger = logging.getLogger(f"threadeye-test-{id(stream)}")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler(stream))
    return logger, stream


async def invoke(app, scope):
    sent = []
    async def receive(): return {"type": "http.request", "body": b"", "more_body": False}
    async def send(message): sent.append(message)
    await app(scope, receive, send)
    return sent


def scope(config, *, method="POST", headers=None):
    values = [(b"host", f"{config.host}:{config.port}".encode())]
    values.extend(headers or [])
    return {
        "type": "http", "method": method, "path": config.path,
        "headers": values, "client": ("127.0.0.1", 12345), "state": {},
    }


class HTTPSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = HTTPAuthorizationConfig.load(ROOT / "config/mcp-http.json")

    def test_rate_limiter_is_bounded_and_recovers_after_window(self) -> None:
        clock = Clock()
        limiter = InMemoryRateLimiter(10.0, 16, clock=clock)
        self.assertTrue(limiter.allow("principal:a", 2)[0])
        self.assertTrue(limiter.allow("principal:a", 2)[0])
        self.assertFalse(limiter.allow("principal:a", 2)[0])
        for index in range(40):
            limiter.allow(f"ip:{index}", 1)
        self.assertLessEqual(limiter.entry_count, 16)
        clock.value = 11.0
        self.assertTrue(limiter.allow("principal:a", 2)[0])

    def test_pre_auth_rejects_rebinding_duplicates_methods_and_large_bodies(self) -> None:
        logger, _ = logger_and_stream()
        called = {"value": False}
        async def downstream(scope, receive, send):
            called["value"] = True
        middleware = PreAuthHTTPSecurityMiddleware(downstream, self.config, logger)
        cases = (
            (scope(self.config, headers=[(b"host", b"evil.example")]), 421),
            (scope(self.config, headers=[(b"origin", b"https://evil.example")]), 403),
            (scope(self.config, headers=[(b"authorization", b"Bearer a"), (b"authorization", b"Bearer b")]), 400),
            (scope(self.config, method="PUT"), 405),
            (scope(self.config, headers=[(b"content-length", str(self.config.max_http_body_bytes + 1).encode())]), 413),
        )
        for request_scope, expected in cases:
            called["value"] = False
            messages = anyio.run(invoke, middleware, request_scope)
            self.assertEqual(messages[0]["status"], expected)
            self.assertFalse(called["value"])

    def test_http_concurrency_exhaustion_returns_429_without_queueing(self) -> None:
        raw = dict(self.config.__dict__)
        raw["max_http_concurrency"] = 1
        config = HTTPAuthorizationConfig(**raw)
        logger, _ = logger_and_stream()
        limiter = InMemoryRateLimiter(60, 16)
        entered = anyio.Event()
        release = anyio.Event()

        async def downstream(scope, receive, send):
            entered.set()
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = PostAuthHTTPControlMiddleware(downstream, config, limiter, logger)

        async def exercise():
            async with anyio.create_task_group() as tasks:
                tasks.start_soon(invoke, middleware, scope(config))
                await entered.wait()
                second = await invoke(middleware, scope(config))
                release.set()
            return second

        messages = anyio.run(exercise)
        self.assertEqual(messages[0]["status"], 429)
        self.assertEqual(json.loads(messages[1]["body"])["error"], "concurrency_limit_exceeded")

    def test_cancellation_releases_http_concurrency_capacity(self) -> None:
        raw = dict(self.config.__dict__)
        raw["max_http_concurrency"] = 1
        config = HTTPAuthorizationConfig(**raw)
        logger, _ = logger_and_stream()
        calls = {"count": 0}

        async def downstream(scope, receive, send):
            calls["count"] += 1
            if calls["count"] == 1:
                await anyio.sleep(10)
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b""})

        middleware = PostAuthHTTPControlMiddleware(
            downstream, config, InMemoryRateLimiter(60, 16), logger
        )

        async def exercise():
            with anyio.move_on_after(0.01):
                await invoke(middleware, scope(config))
            return await invoke(middleware, scope(config))

        messages = anyio.run(exercise)
        self.assertEqual(messages[0]["status"], 200)

    def test_audit_log_is_json_and_does_not_include_raw_sensitive_values(self) -> None:
        logger, stream = logger_and_stream()
        audit_event(
            logger,
            principal="0123456789abcdef",
            operation="search_evidence",
            authorization="allowed",
            http_status=200,
            rate_limit="allowed",
            reason="completed",
        )
        value = stream.getvalue()
        payload = json.loads(value)
        self.assertEqual(payload["transport"], "streamable-http")
        self.assertNotIn("Bearer", value)
        self.assertNotIn("query", value)


if __name__ == "__main__":
    unittest.main()
