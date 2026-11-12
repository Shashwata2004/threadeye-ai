"""Trusted HTTP configuration and asymmetric OAuth access-token verification."""

from __future__ import annotations

import json
import os
import stat
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_REQUEST

from threadeye_evidence.mcp.authorization import AuthorizationConfigurationError
from threadeye_evidence.mcp.http_security import audit_event, principal_digest


METADATA_SCOPE = "evidence:metadata:read"
SEARCH_SCOPE = "evidence:search"
ANSWER_SCOPE = "evidence:answer"
SUPPORTED_SCOPES = frozenset({METADATA_SCOPE, SEARCH_SCOPE, ANSWER_SCOPE})
_REQUIRED_KEYS = frozenset({
    "version", "host", "port", "path", "resource_url", "issuer_url",
    "allowed_algorithm", "required_token_type", "key_id", "token_ttl_seconds",
    "max_token_chars", "principal_scopes", "allowed_origins", "rate_window_seconds",
    "principal_request_limit", "ip_request_limit", "max_rate_limit_entries",
    "max_http_concurrency", "max_http_body_bytes",
})


def _safe_operator_file(path: Path, *, label: str, max_bytes: int) -> Path:
    value = Path(path)
    if value.is_symlink():
        raise AuthorizationConfigurationError(f"trusted {label} cannot be a symlink")
    try:
        metadata = value.stat()
    except OSError as exc:
        raise AuthorizationConfigurationError(f"trusted {label} is unavailable") from exc
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes:
        raise AuthorizationConfigurationError(f"trusted {label} is not a bounded regular file")
    if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise AuthorizationConfigurationError(f"trusted {label} is broadly writable")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise AuthorizationConfigurationError(f"trusted {label} has an unexpected owner")
    return value


@dataclass(frozen=True)
class HTTPAuthorizationConfig:
    version: int
    host: str
    port: int
    path: str
    resource_url: str
    issuer_url: str
    allowed_algorithm: str
    required_token_type: str
    key_id: str
    token_ttl_seconds: int
    max_token_chars: int
    principal_scopes: dict[str, tuple[str, ...]]
    allowed_origins: tuple[str, ...]
    rate_window_seconds: float
    principal_request_limit: int
    ip_request_limit: int
    max_rate_limit_entries: int
    max_http_concurrency: int
    max_http_body_bytes: int
    config_path: Path

    @classmethod
    def load(cls, path: Path) -> "HTTPAuthorizationConfig":
        value = _safe_operator_file(path, label="HTTP configuration", max_bytes=32_768)
        try:
            raw = json.loads(value.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuthorizationConfigurationError("trusted HTTP configuration is invalid") from exc
        if not isinstance(raw, dict) or set(raw) != _REQUIRED_KEYS:
            raise AuthorizationConfigurationError("trusted HTTP configuration fields are invalid")
        if raw["version"] != 1 or raw["host"] != "127.0.0.1" or raw["path"] != "/mcp":
            raise AuthorizationConfigurationError("HTTP transport must use the fixed loopback endpoint shape")
        if isinstance(raw["port"], bool) or not isinstance(raw["port"], int) or not 1024 <= raw["port"] <= 65535:
            raise AuthorizationConfigurationError("HTTP port is outside the safe local range")
        expected_resource = f"http://127.0.0.1:{raw['port']}/mcp"
        if raw["resource_url"] != expected_resource:
            raise AuthorizationConfigurationError("resource URL must exactly match the configured endpoint")
        issuer = urlsplit(raw["issuer_url"] if isinstance(raw["issuer_url"], str) else "")
        if issuer.scheme != "https" or not issuer.hostname or issuer.username or issuer.password or issuer.query or issuer.fragment:
            raise AuthorizationConfigurationError("issuer URL must be an HTTPS authority without credentials or query data")
        if raw["allowed_algorithm"] != "EdDSA" or raw["required_token_type"] != "at+jwt":
            raise AuthorizationConfigurationError("only EdDSA access-token JWTs are permitted")
        if not isinstance(raw["key_id"], str) or not raw["key_id"].strip() or len(raw["key_id"]) > 128:
            raise AuthorizationConfigurationError("token signing key identifier is invalid")
        if not isinstance(raw["token_ttl_seconds"], int) or not 30 <= raw["token_ttl_seconds"] <= 900:
            raise AuthorizationConfigurationError("token lifetime limit is invalid")
        if not isinstance(raw["max_token_chars"], int) or not 1024 <= raw["max_token_chars"] <= 16384:
            raise AuthorizationConfigurationError("token size limit is invalid")
        principals = raw["principal_scopes"]
        if not isinstance(principals, dict) or not principals or len(principals) > 32:
            raise AuthorizationConfigurationError("principal scope allowlist is invalid")
        normalized_principals: dict[str, tuple[str, ...]] = {}
        for principal, scopes in principals.items():
            if not isinstance(principal, str) or not principal or len(principal) > 128:
                raise AuthorizationConfigurationError("principal identity is invalid")
            if not isinstance(scopes, list) or not scopes or len(scopes) != len(set(scopes)):
                raise AuthorizationConfigurationError("principal scopes are invalid")
            if not set(scopes).issubset(SUPPORTED_SCOPES):
                raise AuthorizationConfigurationError("principal contains an unsupported scope")
            normalized_principals[principal] = tuple(scopes)
        expected_origin = f"http://127.0.0.1:{raw['port']}"
        if raw["allowed_origins"] != [expected_origin]:
            raise AuthorizationConfigurationError("only the exact local HTTP origin may be configured")
        numeric_bounds = {
            "principal_request_limit": (1, 10_000),
            "ip_request_limit": (1, 20_000),
            "max_rate_limit_entries": (16, 10_000),
            "max_http_concurrency": (1, 16),
            "max_http_body_bytes": (4_096, 262_144),
        }
        for name, (minimum, maximum) in numeric_bounds.items():
            item = raw[name]
            if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
                raise AuthorizationConfigurationError(f"{name} is outside the safe range")
        window = raw["rate_window_seconds"]
        if isinstance(window, bool) or not isinstance(window, (int, float)) or not 0.1 <= window <= 3600:
            raise AuthorizationConfigurationError("rate-limit window is outside the safe range")
        return cls(
            **{key: raw[key] for key in _REQUIRED_KEYS if key not in {"principal_scopes", "allowed_origins"}},
            principal_scopes=normalized_principals,
            allowed_origins=tuple(raw["allowed_origins"]),
            config_path=value.resolve(),
        )

    @classmethod
    def from_environment(cls) -> "HTTPAuthorizationConfig":
        path = os.environ.get("THREADEYE_EVIDENCE_HTTP_CONFIG")
        if not path:
            raise AuthorizationConfigurationError("trusted HTTP authorization configuration is missing")
        return cls.load(Path(path))

    def public_mapping(self) -> dict[str, Any]:
        return {
            "transport": "streamable-http",
            "endpoint": self.resource_url,
            "issuer": self.issuer_url,
            "supported_scopes": sorted(SUPPORTED_SCOPES),
            "signing_algorithm": self.allowed_algorithm,
            "stateless": True,
            "rate_limits": {
                "window_seconds": self.rate_window_seconds,
                "per_principal": self.principal_request_limit,
                "per_ip": self.ip_request_limit,
                "max_entries": self.max_rate_limit_entries,
            },
            "max_http_concurrency": self.max_http_concurrency,
            "max_http_body_bytes": self.max_http_body_bytes,
        }


class EdDSAAccessTokenVerifier(TokenVerifier):
    """Validate short-lived asymmetric JWT access tokens against trusted local policy."""

    def __init__(self, config: HTTPAuthorizationConfig, public_key: Ed25519PublicKey) -> None:
        self.config = config
        self.public_key = public_key

    @classmethod
    def from_environment(cls, config: HTTPAuthorizationConfig) -> "EdDSAAccessTokenVerifier":
        path = os.environ.get("THREADEYE_EVIDENCE_HTTP_PUBLIC_KEY")
        if not path:
            raise AuthorizationConfigurationError("trusted HTTP token verification key is missing")
        value = _safe_operator_file(Path(path), label="HTTP public key", max_bytes=8_192)
        try:
            key = load_pem_public_key(value.read_bytes())
        except (OSError, ValueError, TypeError) as exc:
            raise AuthorizationConfigurationError("trusted HTTP public key is invalid") from exc
        if not isinstance(key, Ed25519PublicKey):
            raise AuthorizationConfigurationError("trusted HTTP public key must be Ed25519")
        return cls(config, key)

    async def verify_token(self, token: str) -> AccessToken | None:
        if not isinstance(token, str) or not token or len(token) > self.config.max_token_chars:
            return None
        try:
            header = jwt.get_unverified_header(token)
            if (
                header.get("alg") != self.config.allowed_algorithm
                or header.get("typ") != self.config.required_token_type
                or header.get("kid") != self.config.key_id
            ):
                return None
            claims = jwt.decode(
                token,
                self.public_key,
                algorithms=[self.config.allowed_algorithm],
                audience=self.config.resource_url,
                issuer=self.config.issuer_url,
                options={
                    "require": ["iss", "aud", "exp", "iat", "sub", "client_id", "scope", "jti", "token_use"],
                },
            )
        except (jwt.PyJWTError, ValueError, TypeError):
            return None
        now = int(time.time())
        subject = claims.get("sub")
        client_id = claims.get("client_id")
        issued_at = claims.get("iat")
        expires_at = claims.get("exp")
        not_before = claims.get("nbf")
        token_id = claims.get("jti")
        scope_text = claims.get("scope")
        if (
            not isinstance(subject, str)
            or not subject
            or subject != client_id
            or subject not in self.config.principal_scopes
            or claims.get("token_use") != "access"
            or isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
            or (not_before is not None and (isinstance(not_before, bool) or not isinstance(not_before, int)))
            or not isinstance(token_id, str)
            or not token_id
            or len(token_id) > 128
            or issued_at > now
            or expires_at <= issued_at
            or expires_at - issued_at > self.config.token_ttl_seconds
            or not isinstance(scope_text, str)
        ):
            return None
        scopes = scope_text.split()
        if not scopes or len(scopes) != len(set(scopes)):
            return None
        allowed = set(self.config.principal_scopes[subject])
        if not set(scopes).issubset(allowed) or not set(scopes).issubset(SUPPORTED_SCOPES):
            return None
        return AccessToken(
            token=token,
            client_id=client_id,
            subject=subject,
            scopes=scopes,
            expires_at=expires_at,
            resource=self.config.resource_url,
            claims={"token_type": self.config.required_token_type, "issuer": self.config.issuer_url},
        )


class HTTPScopeAuthorizationMiddleware:
    """Apply least-privilege scopes per tool/resource using request-local SDK auth context."""

    TOOL_SCOPES = {
        "search_evidence": SEARCH_SCOPE,
        "answer_evidence_question": ANSWER_SCOPE,
        "list_evidence_sources": METADATA_SCOPE,
        "get_evidence_capabilities": METADATA_SCOPE,
    }

    def __init__(self, logger) -> None:
        self.logger = logger

    @staticmethod
    def _required_scope(ctx: ServerRequestContext[Any, Any]) -> tuple[str | None, str]:
        if ctx.method == "tools/call" and isinstance(ctx.params, Mapping):
            name = ctx.params.get("name")
            if isinstance(name, str) and name in HTTPScopeAuthorizationMiddleware.TOOL_SCOPES:
                return HTTPScopeAuthorizationMiddleware.TOOL_SCOPES[name], name
            return None, "unknown_tool"
        if ctx.method == "resources/read":
            return METADATA_SCOPE, "resource_read"
        return None, "protocol_request"

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        required, operation = self._required_scope(ctx)
        if required is None:
            return await call_next(ctx)
        token = get_access_token()
        authorized = token is not None and required in token.scopes
        audit_event(
            self.logger,
            principal=principal_digest(token.subject if token else None),
            operation=operation,
            authorization="allowed" if authorized else "denied",
            mcp_category="authorized" if authorized else "insufficient_scope",
            rate_limit="handled_at_http_boundary",
            reason="scope_satisfied" if authorized else "scope_required",
        )
        if not authorized:
            raise MCPError(code=INVALID_REQUEST, message="Not authorized for requested operation")
        return await call_next(ctx)
