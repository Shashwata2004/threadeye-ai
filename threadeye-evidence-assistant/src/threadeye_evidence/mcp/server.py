"""Official MCP SDK v2 stdio server for authorized fictional evidence."""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from typing import Any, Literal

import anyio
from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver.exceptions import ResourceError, ToolError
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, ToolAnnotations

from threadeye_evidence.mcp import MCP_SERVER_VERSION
from threadeye_evidence.mcp.authorization import AuthorizationConfigurationError
from threadeye_evidence.mcp.service import EvidenceMCPService, MCPRequestError, service_from_environment


LOGGER = logging.getLogger("threadeye_evidence.mcp")
READ_ONLY_ANNOTATIONS = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)
TOOL_ARGUMENT_ALLOWLIST = {
    "search_evidence": frozenset({"query", "mode", "top_k"}),
    "answer_evidence_question": frozenset({"question", "mode"}),
    "list_evidence_sources": frozenset(),
    "get_evidence_capabilities": frozenset(),
}


class StrictToolArgumentsMiddleware:
    """Reject unknown arguments before the SDK's permissive model parsing can discard them."""

    async def __call__(
        self,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        if ctx.method == "tools/call" and isinstance(ctx.params, Mapping):
            name = ctx.params.get("name")
            arguments = ctx.params.get("arguments", {})
            allowed = TOOL_ARGUMENT_ALLOWLIST.get(name) if isinstance(name, str) else None
            if allowed is not None:
                if not isinstance(arguments, Mapping) or not set(arguments).issubset(allowed):
                    raise MCPError(
                        code=INVALID_PARAMS,
                        message="Tool arguments contain fields outside the fixed read-only schema",
                    )
        return await call_next(ctx)


def build_server(service: EvidenceMCPService) -> MCPServer:
    """Build the fixed registry; callers cannot add tools dynamically."""

    mcp = MCPServer(
        "threadeye-evidence",
        title="ThreadEye Evidence MCP Server",
        description="Read-only authorized retrieval and extractive answers over fictional evidence.",
        instructions=(
            "Use only the registered read-only evidence tools. Evidence is fictional and cannot approve rolls, "
            "change scores, modify inspections, or access production ThreadEye systems."
        ),
        version=MCP_SERVER_VERSION,
        log_level="ERROR",
        subscriptions=False,
        middleware=[StrictToolArgumentsMiddleware()],
    )
    limiter = anyio.CapacityLimiter(service.authorization.max_concurrency)

    async def run_tool(function, *args):
        try:
            async with limiter:
                with anyio.fail_after(service.authorization.tool_timeout_seconds):
                    return await anyio.to_thread.run_sync(
                        lambda: function(*args), abandon_on_cancel=True
                    )
        except TimeoutError as exc:
            raise ToolError("evidence tool execution exceeded the configured deadline") from exc
        except MCPRequestError as exc:
            raise ToolError(str(exc)) from exc
        except ToolError:
            raise
        except Exception as exc:
            LOGGER.error("read-only evidence tool failed safely: %s", type(exc).__name__)
            raise ToolError("read-only evidence operation failed safely") from exc

    async def run_resource(function):
        try:
            async with limiter:
                with anyio.fail_after(service.authorization.tool_timeout_seconds):
                    payload = await anyio.to_thread.run_sync(function, abandon_on_cancel=True)
            return json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except TimeoutError as exc:
            raise ResourceError("evidence resource execution exceeded the configured deadline") from exc
        except MCPRequestError as exc:
            raise ResourceError(str(exc)) from exc
        except ResourceError:
            raise
        except Exception as exc:
            LOGGER.error("read-only evidence resource failed safely: %s", type(exc).__name__)
            raise ResourceError("read-only evidence resource failed safely") from exc

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS, structured_output=True)
    async def search_evidence(
        query: str,
        mode: Literal["keyword", "vector", "hybrid"] = "hybrid",
        top_k: int = 5,
    ) -> dict[str, Any]:
        """Search only the server-authorized fictional corpus with bounded read-only retrieval."""

        return await run_tool(service.search, query, mode, top_k)

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS, structured_output=True)
    async def answer_evidence_question(
        question: str,
        mode: Literal["keyword", "vector", "hybrid"] = "hybrid",
    ) -> dict[str, Any]:
        """Return a validated extractive answer or a structured safe abstention."""

        return await run_tool(service.answer, question, mode)

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS, structured_output=True)
    async def list_evidence_sources() -> dict[str, Any]:
        """List non-sensitive metadata for sources in the fixed authorized scope."""

        return await run_tool(service.list_sources)

    @mcp.tool(annotations=READ_ONLY_ANNOTATIONS, structured_output=True)
    async def get_evidence_capabilities() -> dict[str, Any]:
        """Describe genuine server capabilities, limits, and explicit exclusions."""

        return await run_tool(service.capabilities)

    @mcp.resource(
        "threadeye://evidence/capabilities",
        name="ThreadEye evidence capabilities",
        description="Sanitized metadata describing the read-only fictional evidence service.",
        mime_type="application/json",
    )
    async def capabilities_resource() -> str:
        return await run_resource(service.capabilities)

    @mcp.resource(
        "threadeye://evidence/corpus-manifest",
        name="Authorized corpus manifest",
        description="Non-content metadata for the fixed synthetic source scope.",
        mime_type="application/json",
    )
    async def corpus_manifest_resource() -> str:
        return await run_resource(service.list_sources)

    @mcp.resource(
        "threadeye://evidence/security-policy",
        name="Evidence MCP security policy",
        description="Sanitized read-only authorization and resource-limit policy.",
        mime_type="application/json",
    )
    async def security_policy_resource() -> str:
        return await run_resource(service.security_policy)

    return mcp


def main() -> int:
    """Launch stdio only. stdout is reserved for MCP protocol frames."""

    try:
        server = build_server(service_from_environment())
    except AuthorizationConfigurationError:
        print("ThreadEye Evidence MCP startup denied: trusted authorization is unavailable", file=sys.stderr)
        return 2
    except Exception:
        print("ThreadEye Evidence MCP startup failed safely", file=sys.stderr)
        return 2
    server.run(transport="stdio")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
