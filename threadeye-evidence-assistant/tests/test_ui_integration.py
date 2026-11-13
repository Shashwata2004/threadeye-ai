from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

import anyio

from threadeye_evidence.mcp.verify_http import _required_environment, _start_server, _temporary_http_fixture, _wait_ready
from threadeye_evidence.ui.mcp_client import MCPHTTPGateway


RUN = (
    os.environ.get("THREADEYE_RUN_DB_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_MODEL_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_MCP_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_HTTP_TESTS") == "1"
    and os.environ.get("THREADEYE_RUN_UI_TESTS") == "1"
    and os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL")
)


async def genuine_ui_gateway_flow() -> dict:
    project, environment = _required_environment()
    with tempfile.TemporaryDirectory(prefix="threadeye-ui-integration-") as temporary:
        directory = Path(temporary)
        config, private_key, config_path, public_path = _temporary_http_fixture(project, directory)
        stderr_path = directory / "mcp-stderr.log"
        with stderr_path.open("w+", encoding="utf-8") as stderr_file:
            process = _start_server(project, environment, config_path, public_path, stderr_file)
            try:
                await _wait_ready(config, process)
                gateway = MCPHTTPGateway(config, private_key)
                overview = await gateway.overview()
                search = await gateway.search("content hash sanitized observation", "hybrid", 3)
                answer = await gateway.answer("Which supplier lot is recorded for ROLL-NST-204?", "hybrid")
                abstention = await gateway.answer("What is tomorrow's weather in Dhaka?", "hybrid")
                return {"overview": overview, "search": search, "answer": answer, "abstention": abstention}
            finally:
                process.terminate()
                process.wait(timeout=5)


@unittest.skipUnless(RUN, "real judge UI MCP/BGE/PostgreSQL integration not requested")
class RealUIIntegrationTests(unittest.TestCase):
    def test_official_http_mcp_search_answer_citation_and_abstention(self) -> None:
        report = anyio.run(genuine_ui_gateway_flow)
        self.assertEqual(report["overview"]["connection"], "CONNECTED")
        self.assertTrue(report["overview"]["capabilities"]["read_only"])
        self.assertEqual(report["search"]["mode"], "hybrid")
        self.assertGreater(report["search"]["result_count"], 0)
        self.assertEqual(report["search"]["results"][0]["retrieval_methods"], ["keyword", "vector"])
        self.assertEqual({item["source_relative_path"] for item in report["search"]["results"]}, {"technical-evidence.md"})
        self.assertEqual(report["answer"]["status"], "answered")
        self.assertTrue(report["answer"]["retrieval_metadata"]["citation_validation"]["valid"])
        self.assertEqual(report["answer"]["answer"], " ".join(item["excerpt"] for item in report["answer"]["citations"]))
        self.assertEqual(report["abstention"]["status"], "insufficient_evidence")
        self.assertIsNone(report["abstention"]["answer"])
        self.assertFalse(report["abstention"]["citations"])


if __name__ == "__main__":
    unittest.main()
