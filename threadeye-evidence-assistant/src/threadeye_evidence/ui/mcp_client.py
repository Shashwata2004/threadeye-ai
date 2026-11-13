"""Narrow official-SDK client used by the local UI backend."""

from __future__ import annotations

import json
import os
import time
from typing import Any

import httpx2
import jwt
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation

from threadeye_evidence.mcp.http_authorization import (
    ANSWER_SCOPE,
    METADATA_SCOPE,
    SEARCH_SCOPE,
    HTTPAuthorizationConfig,
)
from threadeye_evidence.mcp.verify_client import APPROVED_RESOURCES, APPROVED_TOOLS, _payload
from threadeye_evidence.ui import UI_VERSION


class UIGatewayError(RuntimeError):
    public_state = "BACKEND UNAVAILABLE"


class UIUnauthorized(UIGatewayError):
    public_state = "UNAUTHORIZED"


class UIValidationFailure(UIGatewayError):
    public_state = "VALIDATION FAILURE"


class MCPHTTPGateway:
    """Expose four fixed read-only operations; never an arbitrary MCP proxy."""

    def __init__(self, config: HTTPAuthorizationConfig, private_key, *, timeout_seconds: float = 15.0) -> None:
        self.config = config
        self.private_key = private_key
        self.timeout_seconds = timeout_seconds

    def _token(self) -> str:
        now = int(time.time())
        subject = "threadeye-evidence-client"
        claims = {
            "iss": self.config.issuer_url,
            "aud": self.config.resource_url,
            "iat": now,
            "exp": now + min(120, self.config.token_ttl_seconds),
            "sub": subject,
            "client_id": subject,
            "scope": " ".join((METADATA_SCOPE, SEARCH_SCOPE, ANSWER_SCOPE)),
            "jti": os.urandom(16).hex(),
            "token_use": "access",
        }
        return jwt.encode(
            claims,
            self.private_key,
            algorithm=self.config.allowed_algorithm,
            headers={"kid": self.config.key_id, "typ": self.config.required_token_type},
        )

    async def _client(self):
        http_client = httpx2.AsyncClient(
            headers={"Authorization": f"Bearer {self._token()}"},
            timeout=httpx2.Timeout(5.0, read=self.timeout_seconds),
        )
        transport = streamable_http_client(
            self.config.resource_url,
            http_client=http_client,
            terminate_on_close=False,
        )
        return http_client, Client(
            transport,
            mode="legacy",
            read_timeout_seconds=self.timeout_seconds,
            client_info=Implementation(name="threadeye-judge-ui", version=UI_VERSION),
        )

    @staticmethod
    def _checked_payload(result) -> dict[str, Any]:
        if result.is_error:
            rendered = " ".join(str(getattr(block, "text", "")) for block in result.content).lower()
            if "not authorized" in rendered or "insufficient_scope" in rendered:
                raise UIUnauthorized("MCP operation was not authorized")
            raise UIValidationFailure("MCP rejected the bounded request")
        payload = _payload(result)
        if not isinstance(payload, dict):
            raise UIValidationFailure("MCP response shape was invalid")
        return payload

    async def overview(self) -> dict[str, Any]:
        try:
            http_client, client_context = await self._client()
            async with http_client:
                async with client_context as client:
                    tools = await client.list_tools()
                    resources = await client.list_resources()
                    tool_names = {tool.name for tool in tools.tools}
                    resource_names = {str(resource.uri) for resource in resources.resources}
                    if tool_names != APPROVED_TOOLS or resource_names != APPROVED_RESOURCES:
                        raise UIValidationFailure("MCP registry did not match the approved read-only surface")
                    capabilities = self._checked_payload(await client.call_tool("get_evidence_capabilities", {}))
                    sources = self._checked_payload(await client.call_tool("list_evidence_sources", {}))
                    policy_result = await client.read_resource("threadeye://evidence/security-policy")
                    policy = json.loads(policy_result.contents[0].text)
                    if not capabilities.get("read_only") or not policy.get("read_only"):
                        raise UIValidationFailure("MCP read-only policy could not be verified")
                    return {
                        "connection": "CONNECTED",
                        "protocol_version": str(client.protocol_version),
                        "server_version": client.server_info.version if client.server_info else None,
                        "authorization_scopes": [METADATA_SCOPE, SEARCH_SCOPE, ANSWER_SCOPE],
                        "capabilities": capabilities,
                        "sources": sources,
                        "security_policy": policy,
                    }
        except UIGatewayError:
            raise
        except Exception as exc:
            raise UIGatewayError("authenticated MCP backend is unavailable") from exc

    async def search(self, query: str, mode: str, top_k: int) -> dict[str, Any]:
        try:
            http_client, client_context = await self._client()
            async with http_client:
                async with client_context as client:
                    return self._checked_payload(await client.call_tool("search_evidence", {
                        "query": query,
                        "mode": mode,
                        "top_k": top_k,
                    }))
        except UIGatewayError:
            raise
        except Exception as exc:
            raise UIGatewayError("authenticated MCP search is unavailable") from exc

    async def answer(self, question: str, mode: str) -> dict[str, Any]:
        try:
            http_client, client_context = await self._client()
            async with http_client:
                async with client_context as client:
                    return self._checked_payload(await client.call_tool("answer_evidence_question", {
                        "question": question,
                        "mode": mode,
                    }))
        except UIGatewayError:
            raise
        except Exception as exc:
            raise UIGatewayError("authenticated MCP answering is unavailable") from exc
