from __future__ import annotations

import anyio
from types import SimpleNamespace
import time
import unittest

from mcp import Client

from threadeye_evidence.mcp.server import TOOL_ARGUMENT_ALLOWLIST, build_server


class FakeService:
    def __init__(self, timeout: float = 1.0) -> None:
        self.authorization = SimpleNamespace(max_concurrency=1, tool_timeout_seconds=timeout)
    def search(self, query, mode, top_k): return {"status":"ok","query":query,"mode":mode,"top_k":top_k}
    def answer(self, question, mode): return {"status":"insufficient_evidence","question":question,"mode":mode}
    def list_sources(self): return {"source_count":0,"sources":[]}
    def capabilities(self): return {"read_only":True}
    def security_policy(self): return {"read_only":True}


class SlowService(FakeService):
    def search(self, query, mode, top_k):
        time.sleep(0.2)
        return super().search(query, mode, top_k)


async def inspect_server() -> dict[str, object]:
    server = build_server(FakeService())
    async with Client(server, mode="legacy") as client:
        listing = await client.list_tools()
        schemas = {tool.name: tool.input_schema for tool in listing.tools}
        annotations = {tool.name: tool.annotations for tool in listing.tools}
        try:
            await client.call_tool("search_evidence", {"query":"x","corpus_id":"other"})
            extra_rejected = False
        except Exception:
            extra_rejected = True
    return {"schemas":schemas,"annotations":annotations,"extra_rejected":extra_rejected}


async def timeout_server() -> bool:
    server = build_server(SlowService(timeout=0.02))
    async with Client(server, mode="legacy") as client:
        try:
            result = await client.call_tool("search_evidence", {"query":"x","mode":"hybrid","top_k":1})
            return bool(result.is_error)
        except Exception:
            return True


class MCPServerUnitTests(unittest.TestCase):
    def test_tool_schemas_annotations_and_unknown_argument_rejection(self) -> None:
        report = anyio.run(inspect_server)
        self.assertEqual(set(report["schemas"]), set(TOOL_ARGUMENT_ALLOWLIST))
        self.assertEqual(set(report["schemas"]["search_evidence"]["properties"]), {"query","mode","top_k"})
        self.assertTrue(all(annotation.read_only_hint for annotation in report["annotations"].values()))
        self.assertTrue(report["extra_rejected"])

    def test_tool_deadline_fails_safely(self) -> None:
        self.assertTrue(anyio.run(timeout_server))


if __name__ == "__main__":
    unittest.main()
