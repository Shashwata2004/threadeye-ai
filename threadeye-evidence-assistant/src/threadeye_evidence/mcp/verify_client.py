"""Reproducible official-SDK client verification over a real stdio subprocess."""

from __future__ import annotations

import anyio
import json
import os
from pathlib import Path
import sys
from typing import Any

from mcp import Client, StdioServerParameters
from mcp.types import Implementation


APPROVED_TOOLS = {
    "search_evidence",
    "answer_evidence_question",
    "list_evidence_sources",
    "get_evidence_capabilities",
}
APPROVED_RESOURCES = {
    "threadeye://evidence/capabilities",
    "threadeye://evidence/corpus-manifest",
    "threadeye://evidence/security-policy",
}


def _payload(result) -> dict[str, Any]:
    if result.structured_content is not None:
        return dict(result.structured_content)
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise RuntimeError("tool result contained no structured payload")


def _required_environment() -> tuple[Path, dict[str, str]]:
    config = os.environ.get("THREADEYE_EVIDENCE_MCP_CONFIG")
    dsn = os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL")
    cache = os.environ.get("THREADEYE_EVIDENCE_MODEL_CACHE")
    if not config or not dsn or not cache:
        raise RuntimeError("trusted MCP verification environment is incomplete")
    project = Path(__file__).resolve().parents[3]
    return project, {
        "THREADEYE_EVIDENCE_MCP_CONFIG": config,
        "THREADEYE_EVIDENCE_MCP_DATABASE_URL": dsn,
        "THREADEYE_EVIDENCE_MODEL_CACHE": cache,
        "PYTHONDONTWRITEBYTECODE": "1",
    }


async def verify_stdio() -> dict[str, Any]:
    project, environment = _required_environment()
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "threadeye_evidence.mcp.server"],
        env=environment,
        cwd=project,
    )
    report: dict[str, Any] = {}
    async with Client(
        params,
        mode="legacy",
        read_timeout_seconds=15.0,
        client_info=Implementation(name="threadeye-evidence-verifier", version="0.8.0"),
    ) as client:
        report["initialization"] = {
            "protocol_version": str(client.protocol_version),
            "server_name": client.server_info.name if client.server_info else None,
            "server_version": client.server_info.version if client.server_info else None,
            "capabilities_present": client.server_capabilities is not None,
        }
        tools = await client.list_tools()
        tool_names = {tool.name for tool in tools.tools}
        report["tools"] = sorted(tool_names)
        report["tool_allowlist_exact"] = tool_names == APPROVED_TOOLS

        resources = await client.list_resources()
        resource_uris = {str(resource.uri) for resource in resources.resources}
        report["resources"] = sorted(resource_uris)
        report["resource_allowlist_exact"] = resource_uris == APPROVED_RESOURCES
        resource = await client.read_resource("threadeye://evidence/capabilities")
        report["resource_read"] = {
            "content_count": len(resource.contents),
            "mime_type": resource.contents[0].mime_type,
            "read_only": json.loads(resource.contents[0].text)["read_only"],
        }

        search = await client.call_tool("search_evidence", {
            "query": "Which supplier lot is recorded for ROLL-NST-204?",
            "mode": "hybrid",
            "top_k": 3,
        })
        search_payload = _payload(search)
        report["search"] = {
            "is_error": bool(search.is_error),
            "result_count": search_payload["result_count"],
            "source_paths": sorted({row["source_relative_path"] for row in search_payload["results"]}),
            "has_provenance": all(row["chunk_id"] and row["chunk_sha256"] for row in search_payload["results"]),
        }

        answer = await client.call_tool("answer_evidence_question", {
            "question": "Which supplier lot is recorded for ROLL-NST-204?",
            "mode": "hybrid",
        })
        answer_payload = _payload(answer)
        report["answer"] = {
            "is_error": bool(answer.is_error),
            "status": answer_payload["status"],
            "answer_mode": answer_payload["answer_mode"],
            "citation_count": len(answer_payload["citations"]),
            "citation_valid": answer_payload["retrieval_metadata"].get("citation_validation", {}).get("valid"),
        }

        abstention = await client.call_tool("answer_evidence_question", {
            "question": "What is tomorrow's weather in Dhaka?",
        })
        abstention_payload = _payload(abstention)
        report["unsupported"] = {
            "is_error": bool(abstention.is_error),
            "status": abstention_payload["status"],
            "reason": abstention_payload["abstention_reason"],
            "answer_is_null": abstention_payload["answer"] is None,
        }

        try:
            unauthorized = await client.call_tool("search_evidence", {
                "query": "supervisor evidence",
                "mode": "hybrid",
                "top_k": 2,
                "corpus_id": "unauthorized-corpus",
            })
            report["unauthorized_scope_argument"] = {"rejected": bool(unauthorized.is_error)}
        except Exception as exc:
            report["unauthorized_scope_argument"] = {"rejected": True, "error_type": type(exc).__name__}

        try:
            forbidden = await client.call_tool("delete_roll", {"roll_id": "ROLL-NST-204"})
            report["forbidden_tool"] = {"rejected": bool(forbidden.is_error)}
        except Exception as exc:
            report["forbidden_tool"] = {"rejected": True, "error_type": type(exc).__name__}

    report["shutdown"] = "client context exited; stdio subprocess terminated"
    return report


def main() -> int:
    try:
        report = anyio.run(verify_stdio)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
