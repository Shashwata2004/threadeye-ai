"""Request id + CSRF origin check for cookie-authenticated state-changing requests."""

from __future__ import annotations

import uuid
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = rid[:64]
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        return response


class OriginCheckMiddleware(BaseHTTPMiddleware):
    """Browsers send ``Origin`` on state-changing requests. Accept it only from the same host
    (via the proxy / Next.js rewrite) or from an explicitly allowed origin. Requests without
    ``Origin`` are non-browser clients (CLI, tests) and are allowed; the session cookie is
    SameSite=Lax as a second layer."""

    def __init__(self, app: object, allowed: list[str]) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.allowed = set(allowed)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        if request.method in UNSAFE and origin and origin != "null":
            same_host = urlparse(origin).netloc == request.headers.get("host")
            if not same_host and origin not in self.allowed:
                return JSONResponse({"detail": "cross-origin request rejected"}, status_code=403)
        return await call_next(request)
