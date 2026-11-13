"""Explicit authenticated localhost Streamable HTTP entry point."""

from __future__ import annotations

import logging
import sys
from urllib.parse import urlsplit

import uvicorn
from mcp.server.auth.routes import (
    ProtectedResourceMetadata,
    ProtectedResourceMetadataHandler,
    build_resource_metadata_url,
)
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import AnyHttpUrl
from starlette.middleware import Middleware
from starlette.routing import Route

from threadeye_evidence.mcp.authorization import AuthorizationConfigurationError
from threadeye_evidence.mcp.http_authorization import (
    SUPPORTED_SCOPES,
    EdDSAAccessTokenVerifier,
    HTTPAuthorizationConfig,
)
from threadeye_evidence.mcp.http_security import (
    AUDIT_LOGGER_NAME,
    InMemoryRateLimiter,
    PostAuthHTTPControlMiddleware,
    PreAuthHTTPSecurityMiddleware,
)
from threadeye_evidence.mcp.server import build_server
from threadeye_evidence.mcp.service import EvidenceMCPService, service_from_environment


def audit_logger() -> logging.Logger:
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def build_http_app(
    service: EvidenceMCPService,
    config: HTTPAuthorizationConfig,
    verifier: EdDSAAccessTokenVerifier,
    *,
    logger: logging.Logger | None = None,
    rate_limiter: InMemoryRateLimiter | None = None,
):
    logger = logger or audit_logger()
    auth = AuthSettings(
        issuer_url=AnyHttpUrl(config.issuer_url),
        resource_server_url=AnyHttpUrl(config.resource_url),
        required_scopes=[],
        validate_token_resource=True,
    )
    server = build_server(
        service,
        token_verifier=verifier,
        auth=auth,
        enforce_http_scopes=True,
        audit_logger=logger,
    )
    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[f"{config.host}:{config.port}"],
        allowed_origins=list(config.allowed_origins),
    )
    app = server.streamable_http_app(
        streamable_http_path=config.path,
        json_response=True,
        stateless_http=True,
        max_request_body_size=config.max_http_body_bytes,
        max_sessions=1,
        transport_security=security,
        host=config.host,
    )

    metadata_url = build_resource_metadata_url(AnyHttpUrl(config.resource_url))
    metadata_path = urlsplit(str(metadata_url)).path
    app.router.routes = [route for route in app.router.routes if getattr(route, "path", None) != metadata_path]
    metadata = ProtectedResourceMetadata(
        resource=AnyHttpUrl(config.resource_url),
        authorization_servers=[AnyHttpUrl(config.issuer_url)],
        scopes_supported=sorted(SUPPORTED_SCOPES),
        resource_name="ThreadEye Evidence MCP Server",
    )
    metadata_handler = ProtectedResourceMetadataHandler(metadata)
    app.router.routes.append(
        Route(metadata_path, endpoint=metadata_handler.handle, methods=["GET"])
    )

    limiter = rate_limiter or InMemoryRateLimiter(
        config.rate_window_seconds,
        config.max_rate_limit_entries,
    )
    app.user_middleware.append(Middleware(PostAuthHTTPControlMiddleware, config, limiter, logger))
    app.add_middleware(PreAuthHTTPSecurityMiddleware, config=config, logger=logger)
    app.state.threadeye_server = server
    app.state.threadeye_http_config = config
    app.state.threadeye_rate_limiter = limiter
    return app


def app_from_environment():
    config = HTTPAuthorizationConfig.from_environment()
    verifier = EdDSAAccessTokenVerifier.from_environment(config)
    return build_http_app(service_from_environment(), config, verifier), config


def main() -> int:
    try:
        app, config = app_from_environment()
    except AuthorizationConfigurationError:
        print("ThreadEye Evidence HTTP MCP startup denied: trusted authorization is unavailable", file=sys.stderr)
        return 2
    except Exception:
        print("ThreadEye Evidence HTTP MCP startup failed safely", file=sys.stderr)
        return 2
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level="warning",
        access_log=False,
        server_header=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
