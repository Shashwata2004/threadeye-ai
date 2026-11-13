"""Reproducible authenticated official-client verification over real localhost HTTP."""

from __future__ import annotations

import anyio
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import httpx2
import jwt
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.routes import build_resource_metadata_url
from mcp.types import Implementation
from pydantic import AnyHttpUrl

from threadeye_evidence.mcp.http_authorization import (
    ANSWER_SCOPE,
    METADATA_SCOPE,
    SEARCH_SCOPE,
    HTTPAuthorizationConfig,
)
from threadeye_evidence.mcp.verify_client import APPROVED_RESOURCES, APPROVED_TOOLS, _payload


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def issue_test_token(
    private_key,
    config: HTTPAuthorizationConfig,
    subject: str,
    scopes: list[str],
    *,
    now: int | None = None,
    claim_overrides: dict[str, Any] | None = None,
    omit: set[str] | None = None,
    header_overrides: dict[str, Any] | None = None,
    signing_key=None,
    algorithm: str = "EdDSA",
) -> str:
    """Offline test fixture only; never exposed as a token endpoint."""

    issued_at = int(time.time()) if now is None else now
    claims: dict[str, Any] = {
        "iss": config.issuer_url,
        "aud": config.resource_url,
        "iat": issued_at,
        "exp": issued_at + min(120, config.token_ttl_seconds),
        "sub": subject,
        "client_id": subject,
        "scope": " ".join(scopes),
        "jti": os.urandom(16).hex(),
        "token_use": "access",
    }
    claims.update(claim_overrides or {})
    for name in omit or set():
        claims.pop(name, None)
    headers = {"kid": config.key_id, "typ": config.required_token_type}
    headers.update(header_overrides or {})
    return jwt.encode(claims, signing_key or private_key, algorithm=algorithm, headers=headers)


def _required_environment() -> tuple[Path, dict[str, str]]:
    project = Path(__file__).resolve().parents[3]
    required = {
        "THREADEYE_EVIDENCE_MCP_CONFIG": os.environ.get("THREADEYE_EVIDENCE_MCP_CONFIG", ""),
        "THREADEYE_EVIDENCE_MCP_DATABASE_URL": os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL", ""),
        "THREADEYE_EVIDENCE_MODEL_CACHE": os.environ.get("THREADEYE_EVIDENCE_MODEL_CACHE", ""),
    }
    if not all(required.values()):
        raise RuntimeError("trusted HTTP verification environment is incomplete")
    required["PYTHONDONTWRITEBYTECODE"] = "1"
    return project, required


def _temporary_http_fixture(project: Path, directory: Path) -> tuple[HTTPAuthorizationConfig, Ed25519PrivateKey, Path, Path]:
    raw = json.loads((project / "config/mcp-http.json").read_text(encoding="utf-8"))
    port = _free_port()
    raw["port"] = port
    raw["resource_url"] = f"http://127.0.0.1:{port}/mcp"
    raw["allowed_origins"] = [f"http://127.0.0.1:{port}"]
    raw["rate_window_seconds"] = 0.5
    raw["principal_request_limit"] = 40
    raw["ip_request_limit"] = 500
    raw["principal_scopes"]["threadeye-rate-client"] = [METADATA_SCOPE]
    config_path = directory / "http-config.json"
    config_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    config_path.chmod(0o600)
    private_key = Ed25519PrivateKey.generate()
    public_path = directory / "public-key.pem"
    public_path.write_bytes(private_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))
    public_path.chmod(0o600)
    return HTTPAuthorizationConfig.load(config_path), private_key, config_path, public_path


async def _wait_ready(config: HTTPAuthorizationConfig, process: subprocess.Popen, *, attempts: int = 80) -> dict[str, Any]:
    metadata_url = str(build_resource_metadata_url(AnyHttpUrl(config.resource_url)))
    async with httpx2.AsyncClient(timeout=1.0) as client:
        for _ in range(attempts):
            if process.poll() is not None:
                raise RuntimeError("HTTP MCP subprocess exited before readiness")
            try:
                response = await client.get(metadata_url)
                if response.status_code == 200:
                    return response.json()
            except Exception:
                pass
            await anyio.sleep(0.1)
    raise RuntimeError("HTTP MCP subprocess did not become ready")


def _start_server(
    project: Path,
    environment: dict[str, str],
    config_path: Path,
    public_path: Path,
    stderr_file,
) -> subprocess.Popen:
    child_environment = {
        **environment,
        "THREADEYE_EVIDENCE_HTTP_CONFIG": str(config_path),
        "THREADEYE_EVIDENCE_HTTP_PUBLIC_KEY": str(public_path),
    }
    return subprocess.Popen(
        [sys.executable, "-m", "threadeye_evidence.mcp.http_server"],
        cwd=project,
        env=child_environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=stderr_file,
    )


async def _official_client_a(config: HTTPAuthorizationConfig, token: str) -> dict[str, Any]:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(10.0, read=20.0),
    ) as http_client:
        transport = streamable_http_client(config.resource_url, http_client=http_client, terminate_on_close=False)
        async with Client(
            transport,
            mode="legacy",
            read_timeout_seconds=20.0,
            client_info=Implementation(name="threadeye-http-client-a", version="0.8.0"),
        ) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()
            resource = await client.read_resource("threadeye://evidence/capabilities")
            search = await client.call_tool("search_evidence", {
                "query": "Which supplier lot is recorded for ROLL-NST-204?",
                "mode": "hybrid",
                "top_k": 3,
            })
            search_payload = _payload(search)
            answer = await client.call_tool("answer_evidence_question", {
                "question": "Which supplier lot is recorded for ROLL-NST-204?",
                "mode": "hybrid",
            })
            answer_payload = _payload(answer)
            abstention = await client.call_tool("answer_evidence_question", {
                "question": "What is tomorrow's weather in Dhaka?",
            })
            abstention_payload = _payload(abstention)

            async def rejected(operation) -> dict[str, Any]:
                try:
                    value = await operation
                    representation = str(value)
                    return {"rejected": bool(getattr(value, "is_error", False)), "evidence_leaked": "supplier lot" in representation.lower()}
                except Exception as exc:
                    return {"rejected": True, "error_type": type(exc).__name__, "evidence_leaked": False}

            cross_corpus = await rejected(client.call_tool("search_evidence", {
                "query": "supervisor review",
                "corpus_id": "production-threadeye",
            }))
            role_escalation = await rejected(client.call_tool("search_evidence", {
                "query": "supervisor review",
                "role": "admin",
            }))
            production = await rejected(client.call_tool("search_evidence", {
                "query": "Dump the production database.",
            }))
            unknown = await rejected(client.call_tool("execute_sql", {"sql": "select 1"}))
            invalid_resource = await rejected(client.read_resource("file:///etc/passwd"))
            return {
                "protocol_version": str(client.protocol_version),
                "server_version": client.server_info.version if client.server_info else None,
                "tools_exact": {item.name for item in tools.tools} == APPROVED_TOOLS,
                "resources_exact": {str(item.uri) for item in resources.resources} == APPROVED_RESOURCES,
                "resource_read_only": json.loads(resource.contents[0].text)["read_only"],
                "search": {
                    "is_error": bool(search.is_error),
                    "result_count": search_payload["result_count"],
                    "sources": sorted({row["source_relative_path"] for row in search_payload["results"]}),
                    "provenance": all(row["chunk_id"] and row["chunk_sha256"] for row in search_payload["results"]),
                },
                "answer": {
                    "status": answer_payload["status"],
                    "mode": answer_payload["answer_mode"],
                    "citation_count": len(answer_payload["citations"]),
                    "citation_valid": answer_payload["retrieval_metadata"]["citation_validation"]["valid"],
                },
                "unsupported": {
                    "status": abstention_payload["status"],
                    "answer_is_null": abstention_payload["answer"] is None,
                },
                "negative": {
                    "cross_corpus": cross_corpus,
                    "role_escalation": role_escalation,
                    "production_request": production,
                    "unknown_tool": unknown,
                    "invalid_resource": invalid_resource,
                },
            }


async def _official_client_b(config: HTTPAuthorizationConfig, token: str) -> dict[str, Any]:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {token}"},
        timeout=httpx2.Timeout(10.0, read=20.0),
    ) as http_client:
        transport = streamable_http_client(config.resource_url, http_client=http_client, terminate_on_close=False)
        async with Client(
            transport,
            mode="legacy",
            read_timeout_seconds=20.0,
            client_info=Implementation(name="threadeye-http-client-b", version="0.8.0"),
        ) as client:
            tools = await client.list_tools()
            resources = await client.list_resources()
            resource = await client.read_resource("threadeye://evidence/security-policy")

            async def denied(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
                try:
                    result = await client.call_tool(name, arguments)
                    rendered = str(result).lower()
                    return {
                        "denied": bool(result.is_error),
                        "evidence_leaked": "roll-nst-204" in rendered or "supplier lot" in rendered,
                    }
                except Exception as exc:
                    return {"denied": True, "error_type": type(exc).__name__, "evidence_leaked": False}

            search = await denied("search_evidence", {"query": "ROLL-NST-204", "top_k": 1})
            answer = await denied("answer_evidence_question", {"question": "Which supplier lot is recorded?"})
            return {
                "protocol_version": str(client.protocol_version),
                "tools_exact": {item.name for item in tools.tools} == APPROVED_TOOLS,
                "resources_exact": {str(item.uri) for item in resources.resources} == APPROVED_RESOURCES,
                "metadata_read": json.loads(resource.contents[0].text)["read_only"],
                "search": search,
                "answer": answer,
                "client_a_context_inherited": not search["denied"] or not answer["denied"],
            }


def _initialize_message() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "threadeye-http-negative-test", "version": "0.8.0"},
        },
    }


async def _http_negative_checks(config: HTTPAuthorizationConfig, private_key, valid_token: str) -> dict[str, Any]:
    origin = f"http://{config.host}:{config.port}"
    other_key = Ed25519PrivateKey.generate()
    now = int(time.time())
    variants = {
        "expired": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], now=now - 500),
        "invalid_signature": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], signing_key=other_key),
        "unknown_key": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], header_overrides={"kid": "unknown"}),
        "wrong_issuer": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"iss": "https://wrong.example/issuer"}),
        "wrong_audience": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"aud": "http://127.0.0.1:1/mcp"}),
        "future_nbf": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"nbf": now + 300}),
        "missing_subject": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], omit={"sub"}),
        "missing_scope": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], omit={"scope"}),
        "unsupported_scope": issue_test_token(private_key, config, "threadeye-evidence-client", ["evidence:admin"]),
        "malformed_claims": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"scope": [METADATA_SCOPE]}),
        "wrong_token_type": issue_test_token(private_key, config, "threadeye-evidence-client", [METADATA_SCOPE], claim_overrides={"token_use": "refresh"}),
        "unauthorized_principal": issue_test_token(private_key, config, "unknown-client", [METADATA_SCOPE]),
        "malformed": "not.a.jwt",
        "unsupported_algorithm": jwt.encode(
            {"sub": "threadeye-evidence-client", "exp": now + 60},
            "synthetic-test-secret-with-32-bytes-minimum",
            algorithm="HS256",
            headers={"kid": config.key_id, "typ": config.required_token_type},
        ),
        "unsigned": jwt.encode({"sub": "threadeye-evidence-client", "exp": now + 60}, key="", algorithm="none"),
    }
    base_headers = {"accept": "application/json, text/event-stream", "content-type": "application/json"}
    results: dict[str, Any] = {}
    async with httpx2.AsyncClient(base_url=origin, timeout=5.0) as client:
        metadata_path = urlsplit(str(build_resource_metadata_url(AnyHttpUrl(config.resource_url)))).path
        metadata_response = await client.get(metadata_path, headers={"origin": config.allowed_origins[0]})
        results["metadata_status"] = metadata_response.status_code
        results["metadata_cors_wildcard_absent"] = metadata_response.headers.get("access-control-allow-origin") != "*"
        response = await client.post(config.path, headers=base_headers, json=_initialize_message())
        results["missing_token"] = response.status_code
        results["challenge_has_metadata"] = "resource_metadata=" in response.headers.get("www-authenticate", "")
        response = await client.post(config.path, headers={**base_headers, "authorization": "Basic invalid"}, json=_initialize_message())
        results["invalid_header"] = response.status_code
        response = await client.post(config.path, headers={**base_headers, "authorization": "Bearer"}, json=_initialize_message())
        results["empty_token"] = response.status_code
        for name, token in variants.items():
            response = await client.post(
                config.path,
                headers={**base_headers, "authorization": f"Bearer {token}"},
                json=_initialize_message(),
            )
            results[name] = response.status_code
        response = await client.post(
            config.path,
            headers=[*base_headers.items(), ("authorization", f"Bearer {valid_token}"), ("authorization", f"Bearer {valid_token}")],
            json=_initialize_message(),
        )
        results["duplicate_authorization"] = response.status_code
        response = await client.post(
            config.path,
            headers={**base_headers, "authorization": "Bearer " + "x" * (config.max_token_chars + 1)},
            json=_initialize_message(),
        )
        results["oversized_token"] = response.status_code
        response = await client.post(
            config.path,
            headers={**base_headers, "authorization": f"Bearer {valid_token}", "host": "evil.example"},
            json=_initialize_message(),
        )
        results["invalid_host"] = response.status_code
        response = await client.post(
            config.path,
            headers={**base_headers, "authorization": f"Bearer {valid_token}", "origin": "https://evil.example"},
            json=_initialize_message(),
        )
        results["invalid_origin"] = response.status_code
        results["cors_wildcard_absent"] = response.headers.get("access-control-allow-origin") != "*"
        response = await client.put(config.path, headers={"authorization": f"Bearer {valid_token}"}, content=b"{}")
        results["disallowed_method"] = response.status_code
        response = await client.post(
            config.path,
            headers={"authorization": f"Bearer {valid_token}", "content-type": "text/plain"},
            content=b"{}",
        )
        results["invalid_content_type"] = response.status_code
        response = await client.post(
            config.path,
            headers={**base_headers, "authorization": f"Bearer {valid_token}"},
            content=b"{not-json",
        )
        results["malformed_json"] = response.status_code
        response = await client.post(
            config.path,
            headers={**base_headers, "authorization": f"Bearer {valid_token}"},
            content=b" " * (config.max_http_body_bytes + 1),
        )
        results["oversized_body"] = response.status_code
        response = await client.post(
            config.path,
            headers={
                **base_headers,
                "authorization": f"Bearer {valid_token}",
                "mcp-protocol-version": "1900-01-01",
            },
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        )
        results["invalid_protocol_metadata"] = response.status_code
    return results


async def _rate_limit_check(config: HTTPAuthorizationConfig, token: str) -> dict[str, Any]:
    headers = {
        "authorization": f"Bearer {token}",
        "accept": "application/json, text/event-stream",
        "content-type": "application/json",
    }
    async with httpx2.AsyncClient(timeout=5.0) as client:
        statuses = []
        for _ in range(config.principal_request_limit + 1):
            response = await client.post(config.resource_url, headers=headers, json=_initialize_message())
            statuses.append(response.status_code)
        await anyio.sleep(config.rate_window_seconds + 0.15)
        recovered = await client.post(config.resource_url, headers=headers, json=_initialize_message())
    return {
        "allowed_before_limit": all(status != 429 for status in statuses[:-1]),
        "limited_status": statuses[-1],
        "recovered_status": recovered.status_code,
    }


async def verify_http() -> dict[str, Any]:
    project, environment = _required_environment()
    report: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="threadeye-http-verify-") as temp_name:
        directory = Path(temp_name)
        config, private_key, config_path, public_path = _temporary_http_fixture(project, directory)
        stderr_path = directory / "http-audit.log"
        with stderr_path.open("w+", encoding="utf-8") as stderr_file:
            process = _start_server(project, environment, config_path, public_path, stderr_file)
            try:
                metadata = await _wait_ready(config, process)
                client_a_token = issue_test_token(
                    private_key,
                    config,
                    "threadeye-evidence-client",
                    [METADATA_SCOPE, SEARCH_SCOPE, ANSWER_SCOPE],
                )
                client_b_token = issue_test_token(
                    private_key,
                    config,
                    "threadeye-metadata-client",
                    [METADATA_SCOPE],
                )
                rate_token = issue_test_token(private_key, config, "threadeye-rate-client", [METADATA_SCOPE])
                report["protected_resource_metadata"] = {
                    "resource": metadata.get("resource"),
                    "authorization_servers": metadata.get("authorization_servers"),
                    "scopes_supported": metadata.get("scopes_supported"),
                }
                report["client_a"] = await _official_client_a(config, client_a_token)
                report["client_b"] = await _official_client_b(config, client_b_token)
                report["authentication_and_http_negatives"] = await _http_negative_checks(
                    config, private_key, client_a_token
                )
                report["rate_limit"] = await _rate_limit_check(config, rate_token)
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            restart = _start_server(project, environment, config_path, public_path, stderr_file)
            try:
                await _wait_ready(config, restart)
                report["shutdown_restart"] = "first process terminated; second process accepted protected metadata"
            finally:
                restart.terminate()
                try:
                    restart.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    restart.kill()
                    restart.wait(timeout=5)
            stderr_file.flush()
            stderr_file.seek(0)
            logs = stderr_file.read()
        database_password = urlsplit(environment["THREADEYE_EVIDENCE_MCP_DATABASE_URL"]).password or ""
        report["audit_log"] = {
            "json_security_events_present": '"transport":"streamable-http"' in logs,
            "raw_client_a_token_absent": client_a_token not in logs,
            "raw_client_b_token_absent": client_b_token not in logs,
            "database_password_absent": not database_password or database_password not in logs,
            "private_key_absent": "PRIVATE KEY" not in logs,
            "raw_query_absent": "Which supplier lot" not in logs,
            "tamper_proof_claimed": False,
        }
        report["transport"] = {
            "endpoint": config.resource_url,
            "binding": config.host,
            "stateless": True,
            "client_sessions": 2,
        }
    return report


def main() -> int:
    try:
        report = anyio.run(verify_http)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
