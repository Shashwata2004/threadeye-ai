"""Bounded HTTP admission, rate limiting, correlation, and sanitized audit logs."""

from __future__ import annotations

import contextvars
import hashlib
import json
import logging
import threading
import time
import uuid
from collections import OrderedDict, deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

import anyio
from mcp.server.auth.middleware.auth_context import get_access_token

if TYPE_CHECKING:
    from threadeye_evidence.mcp.http_authorization import HTTPAuthorizationConfig


AUDIT_LOGGER_NAME = "threadeye_evidence.http.audit"
correlation_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "threadeye_http_correlation_id", default=None
)


def principal_digest(value: str | None) -> str:
    if not value:
        return "anonymous"
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]


def audit_event(logger: logging.Logger, **fields: Any) -> None:
    payload = {
        "timestamp": int(time.time()),
        "correlation_id": correlation_id_var.get() or "unavailable",
        "transport": "streamable-http",
        **fields,
    }
    logger.info(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


class InMemoryRateLimiter:
    """Bounded fixed-window state with deterministic cleanup; local process only."""

    def __init__(self, window_seconds: float, max_entries: int, *, clock: Callable[[], float] = time.monotonic) -> None:
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        self.clock = clock
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = threading.Lock()

    def allow(self, key: str, limit: int) -> tuple[bool, float]:
        now = self.clock()
        cutoff = now - self.window_seconds
        with self._lock:
            for existing in list(self._events):
                queue = self._events[existing]
                while queue and queue[0] <= cutoff:
                    queue.popleft()
                if not queue:
                    del self._events[existing]
            queue = self._events.setdefault(key, deque())
            self._events.move_to_end(key)
            if len(queue) >= limit:
                return False, max(0.0, self.window_seconds - (now - queue[0]))
            queue.append(now)
            while len(self._events) > self.max_entries:
                self._events.popitem(last=False)
            return True, 0.0

    @property
    def entry_count(self) -> int:
        with self._lock:
            return len(self._events)


async def _json_response(send, status: int, payload: dict[str, Any], headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    response_headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())]
    response_headers.extend(headers or [])
    await send({"type": "http.response.start", "status": status, "headers": response_headers})
    await send({"type": "http.response.body", "body": body})


class PreAuthHTTPSecurityMiddleware:
    """Reject malformed or rebinding-prone requests before token verification."""

    def __init__(self, app, config: HTTPAuthorizationConfig, logger: logging.Logger) -> None:
        self.app = app
        self.config = config
        self.logger = logger
        self.allowed_host = f"{config.host}:{config.port}"

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        correlation_id = uuid.uuid4().hex
        token = correlation_id_var.set(correlation_id)
        try:
            headers = [(name.lower(), value) for name, value in scope.get("headers", [])]
            authorization = [value for name, value in headers if name == b"authorization"]
            host_values = [value.decode("latin-1") for name, value in headers if name == b"host"]
            origins = [value.decode("latin-1") for name, value in headers if name == b"origin"]
            content_lengths = [value for name, value in headers if name == b"content-length"]
            rejection: tuple[int, str] | None = None
            if len(host_values) != 1 or host_values[0] != self.allowed_host:
                rejection = (421, "invalid_host")
            elif len(origins) > 1 or (origins and origins[0] not in self.config.allowed_origins):
                rejection = (403, "invalid_origin")
            elif len(authorization) > 1:
                rejection = (400, "duplicate_authorization")
            elif authorization and len(authorization[0]) > self.config.max_token_chars + 7:
                rejection = (431, "authorization_too_large")
            elif scope.get("path") == self.config.path and scope.get("method") not in {"POST", "GET", "DELETE"}:
                rejection = (405, "method_not_allowed")
            elif len(content_lengths) > 1:
                rejection = (400, "duplicate_content_length")
            elif content_lengths:
                try:
                    if int(content_lengths[0]) > self.config.max_http_body_bytes:
                        rejection = (413, "request_body_too_large")
                except (TypeError, ValueError):
                    rejection = (400, "invalid_content_length")
            if rejection:
                status, reason = rejection
                audit_event(
                    self.logger,
                    principal="anonymous",
                    operation="http_admission",
                    authorization="denied",
                    http_status=status,
                    rate_limit="not_evaluated",
                    reason=reason,
                )
                await _json_response(send, status, {"error": reason})
                return
            scope.setdefault("state", {})["threadeye_correlation_id"] = correlation_id
            await self.app(scope, receive, send)
        finally:
            correlation_id_var.reset(token)


class PostAuthHTTPControlMiddleware:
    """Apply per-principal/IP limits and bounded HTTP concurrency after SDK authentication."""

    def __init__(
        self,
        app,
        config: HTTPAuthorizationConfig,
        limiter: InMemoryRateLimiter,
        logger: logging.Logger,
    ) -> None:
        self.app = app
        self.config = config
        self.limiter = limiter
        self.logger = logger
        self.concurrency = anyio.CapacityLimiter(config.max_http_concurrency)

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http" or scope.get("path") != self.config.path:
            await self.app(scope, receive, send)
            return
        started = time.monotonic()
        access_token = get_access_token()
        principal = principal_digest(access_token.subject if access_token else None)
        client_host = (scope.get("client") or ("unknown", 0))[0]
        ip_key = "ip:" + principal_digest(str(client_host))
        principal_allowed = True
        retry_after = 0.0
        if access_token:
            principal_allowed, retry_after = self.limiter.allow(
                "principal:" + principal, self.config.principal_request_limit
            )
        ip_allowed, ip_retry = self.limiter.allow(ip_key, self.config.ip_request_limit)
        if not principal_allowed or not ip_allowed:
            retry_after = max(retry_after, ip_retry)
            audit_event(
                self.logger,
                principal=principal,
                operation="http_request",
                authorization="authenticated" if access_token else "unauthenticated",
                http_status=429,
                rate_limit="denied",
                reason="rate_limit_exceeded",
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
            await _json_response(
                send,
                429,
                {"error": "rate_limit_exceeded"},
                [(b"retry-after", str(max(1, int(retry_after + 0.999))).encode())],
            )
            return
        try:
            self.concurrency.acquire_nowait()
        except anyio.WouldBlock:
            audit_event(
                self.logger,
                principal=principal,
                operation="http_request",
                authorization="authenticated" if access_token else "unauthenticated",
                http_status=429,
                rate_limit="concurrency_denied",
                reason="concurrency_limit_exceeded",
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
            await _json_response(send, 429, {"error": "concurrency_limit_exceeded"}, [(b"retry-after", b"1")])
            return
        status = 500

        async def capture(message) -> None:
            nonlocal status
            if message.get("type") == "http.response.start":
                status = int(message.get("status", 500))
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            self.concurrency.release()
            denied = status in {401, 403}
            if status == 401:
                reason = "authentication_failed"
            elif status == 403:
                reason = "authorization_or_origin_denied"
            elif status >= 400:
                reason = "request_failed_safely"
            else:
                reason = "completed"
            audit_event(
                self.logger,
                principal=principal,
                operation="http_request",
                authorization="denied" if denied else ("authenticated" if access_token else "unauthenticated"),
                http_status=status,
                rate_limit="allowed",
                reason=reason,
                duration_ms=round((time.monotonic() - started) * 1000, 3),
            )
