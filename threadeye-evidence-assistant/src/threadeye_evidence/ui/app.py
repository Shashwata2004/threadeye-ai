"""Starlette backend-for-frontend for the localhost judge demonstration."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from threadeye_evidence.ui.mcp_client import UIGatewayError, UIUnauthorized, UIValidationFailure
from threadeye_evidence.ui.security import PREAUTH_COOKIE, SESSION_COOKIE, BrowserSession, SessionStore


ASSET_ROOT = Path(__file__).with_name("static")
MODES = frozenset({"keyword", "vector", "hybrid"})
MAX_BODY_BYTES = 8_192


@dataclass(frozen=True)
class UIConfig:
    host: str = "127.0.0.1"
    port: int = 8770
    session_idle_seconds: int = 900
    session_absolute_seconds: int = 1_800
    enforce_loopback_client: bool = True

    def __post_init__(self) -> None:
        if self.host != "127.0.0.1":
            raise ValueError("judge UI must bind to 127.0.0.1")
        if isinstance(self.port, bool) or not 1024 <= self.port <= 65_535:
            raise ValueError("judge UI port must be from 1024 through 65535")

    @property
    def origin(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def authority(self) -> str:
        return f"{self.host}:{self.port}"


class LocalBoundaryMiddleware:
    """Reject non-loopback, rebinding, cross-origin, and oversized browser requests."""

    def __init__(self, app, config: UIConfig) -> None:
        self.app = app
        self.config = config

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        headers = [(name.lower(), value) for name, value in scope.get("headers", [])]
        hosts = [value.decode("latin-1") for name, value in headers if name == b"host"]
        origins = [value.decode("latin-1") for name, value in headers if name == b"origin"]
        fetch_sites = [value.decode("latin-1") for name, value in headers if name == b"sec-fetch-site"]
        lengths = [value for name, value in headers if name == b"content-length"]
        client_host = str((scope.get("client") or ("", 0))[0])
        rejection: tuple[int, str] | None = None
        if hosts != [self.config.authority]:
            rejection = (421, "invalid_host")
        elif self.config.enforce_loopback_client and client_host not in {"127.0.0.1", "::1"}:
            rejection = (403, "loopback_required")
        elif scope.get("method") in {"POST", "PUT", "PATCH", "DELETE"}:
            exact_origin = origins == [self.config.origin]
            browser_same_origin = not origins and fetch_sites == ["same-origin"]
            if not exact_origin and not browser_same_origin:
                rejection = (403, "invalid_origin")
        elif len(lengths) > 1:
            rejection = (400, "duplicate_content_length")
        elif lengths:
            try:
                if int(lengths[0]) > MAX_BODY_BYTES:
                    rejection = (413, "request_body_too_large")
            except (TypeError, ValueError):
                rejection = (400, "invalid_content_length")
        if rejection:
            response = JSONResponse({"state": "VALIDATION FAILURE", "error": rejection[1]}, status_code=rejection[0])
            await self._send(response, scope, receive, send)
            return
        await self._send(self.app, scope, receive, send)

    async def _send(self, application, scope, receive, send) -> None:
        async def with_headers(message) -> None:
            if message.get("type") == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend([
                    (b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"same-origin"),
                    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
                    (b"cache-control", b"no-store"),
                ])
                message["headers"] = headers
            await send(message)

        if isinstance(application, Response):
            await application(scope, receive, with_headers)
        else:
            await application(scope, receive, with_headers)


def _render(name: str, replacements: dict[str, str]) -> str:
    text = (ASSET_ROOT / name).read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", html.escape(value, quote=True))
    return text


def _set_cookie(response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=False,
        samesite="strict",
        path="/",
    )


def _session(request: Request) -> tuple[str | None, BrowserSession | None]:
    identifier = request.cookies.get(SESSION_COOKIE)
    return identifier, request.app.state.sessions.get(identifier)


def _json_state(state: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"state": state, "message": message}, status_code=status_code)


def _authorized(request: Request, *, csrf: bool) -> tuple[str, BrowserSession] | JSONResponse:
    identifier, state = _session(request)
    if identifier is None or state is None:
        return _json_state("UNAUTHORIZED", "Local judge session is missing or expired.", 401)
    if csrf and not request.app.state.sessions.csrf_valid(identifier, request.headers.get("x-csrf-token")):
        return _json_state("UNAUTHORIZED", "CSRF validation failed.", 403)
    return identifier, state


async def _bounded_json(request: Request, allowed: set[str]) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
        raise ValueError("application/json is required")
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("request body must be valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != allowed:
        raise ValueError("request fields do not match the fixed schema")
    return payload


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field} must be text")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be empty")
    if len(normalized) > 1_000:
        raise ValueError(f"{field} must not exceed 1,000 characters")
    if any(ord(character) < 0x20 and character not in "\t\n\r" for character in normalized):
        raise ValueError(f"{field} contains unsupported control characters")
    return normalized


def _mode(value: Any) -> str:
    if not isinstance(value, str) or value not in MODES:
        raise ValueError("mode must be keyword, vector, or hybrid")
    return value


async def home(request: Request) -> Response:
    _, state = _session(request)
    if state is not None:
        return HTMLResponse(_render("dashboard.html", {"csrf_token": state.csrf_token}))
    preauth, csrf = request.app.state.sessions.new_preauth()
    response = HTMLResponse(_render("login.html", {"csrf_token": csrf, "error": ""}))
    _set_cookie(response, PREAUTH_COOKIE, preauth, 300)
    return response


async def login(request: Request) -> Response:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != "application/x-www-form-urlencoded":
        return _json_state("VALIDATION FAILURE", "Form encoding is required.", 415)
    raw = await request.body()
    try:
        values = parse_qs(raw.decode("utf-8"), strict_parsing=True, keep_blank_values=True)
    except (UnicodeError, ValueError):
        values = {}
    if set(values) == {"csrf_token", "access_code"} and all(len(item) == 1 for item in values.values()):
        result = request.app.state.sessions.login(
            request.cookies.get(PREAUTH_COOKIE, ""),
            values["csrf_token"][0],
            values["access_code"][0],
            str(request.client.host if request.client else "unknown"),
        )
    else:
        result = None
    if result:
        identifier, _ = result
        response = RedirectResponse("/", status_code=303)
        _set_cookie(response, SESSION_COOKIE, identifier, request.app.state.config.session_absolute_seconds)
        response.delete_cookie(PREAUTH_COOKIE, path="/")
        return response
    preauth, csrf = request.app.state.sessions.new_preauth()
    response = HTMLResponse(
        _render("login.html", {"csrf_token": csrf, "error": "Access denied. Check the operator-provided local code."}),
        status_code=401,
    )
    _set_cookie(response, PREAUTH_COOKIE, preauth, 300)
    return response


async def logout(request: Request) -> Response:
    auth = _authorized(request, csrf=True)
    if isinstance(auth, JSONResponse):
        return auth
    identifier, _ = auth
    request.app.state.sessions.revoke(identifier)
    response = JSONResponse({"state": "SIGNED OUT"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


async def overview(request: Request) -> Response:
    auth = _authorized(request, csrf=False)
    if isinstance(auth, JSONResponse):
        return auth
    try:
        payload = await request.app.state.gateway.overview()
        return JSONResponse({"state": "CONNECTED", "data": payload})
    except UIGatewayError as exc:
        return _json_state(exc.public_state, str(exc), 503 if not isinstance(exc, UIUnauthorized) else 403)


async def search(request: Request) -> Response:
    auth = _authorized(request, csrf=True)
    if isinstance(auth, JSONResponse):
        return auth
    try:
        payload = await _bounded_json(request, {"query", "mode", "top_k"})
        query = _text(payload["query"], "query")
        mode = _mode(payload["mode"])
        top_k = payload["top_k"]
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
            raise ValueError("top_k must be from 1 through 5")
        result = await request.app.state.gateway.search(query, mode, top_k)
        if result.get("status") != "ok" or not isinstance(result.get("results"), list):
            raise UIValidationFailure("MCP search response failed validation")
        return JSONResponse({"state": "RESULTS READY", "data": result})
    except ValueError as exc:
        return _json_state("VALIDATION FAILURE", str(exc), 400)
    except UIGatewayError as exc:
        status = 403 if isinstance(exc, UIUnauthorized) else 422 if isinstance(exc, UIValidationFailure) else 503
        return _json_state(exc.public_state, str(exc), status)


def _validated_answer(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    status = payload.get("status")
    answer = payload.get("answer")
    citations = payload.get("citations")
    if not isinstance(citations, list):
        raise UIValidationFailure("Answer citations were malformed")
    if status == "answered":
        validation = payload.get("retrieval_metadata", {}).get("citation_validation", {})
        excerpts = [item.get("excerpt") for item in citations if isinstance(item, dict)]
        if (
            not isinstance(answer, str)
            or not answer
            or not citations
            or not validation.get("valid")
            or any(not isinstance(excerpt, str) for excerpt in excerpts)
            or answer != " ".join(excerpts)
        ):
            raise UIValidationFailure("Verified extractive citation contract was not satisfied")
        return "ANSWERED", payload
    if answer is not None or citations:
        raise UIValidationFailure("Abstention response contained an answer or citation")
    states = {
        "insufficient_evidence": "ABSTAINED",
        "unsupported_request": "ABSTAINED",
        "unauthorized": "UNAUTHORIZED",
        "retrieval_error": "BACKEND UNAVAILABLE",
        "citation_validation_failed": "VALIDATION FAILURE",
        "validation_error": "VALIDATION FAILURE",
    }
    if status not in states:
        raise UIValidationFailure("Answer state was not recognized")
    return states[status], payload


async def answer(request: Request) -> Response:
    auth = _authorized(request, csrf=True)
    if isinstance(auth, JSONResponse):
        return auth
    try:
        body = await _bounded_json(request, {"question", "mode"})
        payload = await request.app.state.gateway.answer(_text(body["question"], "question"), _mode(body["mode"]))
        state, checked = _validated_answer(payload)
        status_code = 200 if state in {"ANSWERED", "ABSTAINED"} else 403 if state == "UNAUTHORIZED" else 503 if state == "BACKEND UNAVAILABLE" else 422
        return JSONResponse({"state": state, "data": checked}, status_code=status_code)
    except ValueError as exc:
        return _json_state("VALIDATION FAILURE", str(exc), 400)
    except UIGatewayError as exc:
        status = 403 if isinstance(exc, UIUnauthorized) else 422 if isinstance(exc, UIValidationFailure) else 503
        return _json_state(exc.public_state, str(exc), status)


async def styles(_: Request) -> Response:
    return FileResponse(ASSET_ROOT / "styles.css", media_type="text/css")


async def script(_: Request) -> Response:
    return FileResponse(ASSET_ROOT / "app.js", media_type="text/javascript")


async def health(request: Request) -> Response:
    if request.client and request.app.state.config.enforce_loopback_client and request.client.host not in {"127.0.0.1", "::1"}:
        return JSONResponse({"status": "denied"}, status_code=403)
    return JSONResponse({"status": "ok", "binding": "loopback", "mcp_checked": False})


async def favicon(_: Request) -> Response:
    return Response(status_code=204)


def build_ui_app(gateway, access_code: str, *, config: UIConfig | None = None) -> Starlette:
    active = config or UIConfig()
    routes = [
        Route("/", home, methods=["GET"]),
        Route("/session", login, methods=["POST"]),
        Route("/api/logout", logout, methods=["POST"]),
        Route("/api/overview", overview, methods=["GET"]),
        Route("/api/search", search, methods=["POST"]),
        Route("/api/answer", answer, methods=["POST"]),
        Route("/assets/styles.css", styles, methods=["GET"]),
        Route("/assets/app.js", script, methods=["GET"]),
        Route("/healthz", health, methods=["GET"]),
        Route("/favicon.ico", favicon, methods=["GET"]),
    ]
    app = Starlette(routes=routes, middleware=[Middleware(LocalBoundaryMiddleware, config=active)])
    app.state.config = active
    app.state.gateway = gateway
    app.state.sessions = SessionStore(
        access_code,
        idle_seconds=active.session_idle_seconds,
        absolute_seconds=active.session_absolute_seconds,
    )
    return app
