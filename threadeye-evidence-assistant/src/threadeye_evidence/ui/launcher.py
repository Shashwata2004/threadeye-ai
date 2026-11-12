"""Development-only launcher for the authenticated MCP server and local judge UI."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import httpx2
import uvicorn

from threadeye_evidence.mcp.http_authorization import HTTPAuthorizationConfig
from threadeye_evidence.ui.app import UIConfig, build_ui_app
from threadeye_evidence.ui.mcp_client import MCPHTTPGateway


def _port_available(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex((host, port)) != 0


def _required_environment(project: Path) -> dict[str, str]:
    required = {
        "THREADEYE_EVIDENCE_MCP_CONFIG": os.environ.get("THREADEYE_EVIDENCE_MCP_CONFIG", ""),
        "THREADEYE_EVIDENCE_MCP_DATABASE_URL": os.environ.get("THREADEYE_EVIDENCE_MCP_DATABASE_URL", ""),
        "THREADEYE_EVIDENCE_MODEL_CACHE": os.environ.get("THREADEYE_EVIDENCE_MODEL_CACHE", ""),
    }
    if not all(required.values()):
        raise RuntimeError("trusted MCP configuration, read-only database URL, and model cache are required")
    if not os.environ.get("THREADEYE_EVIDENCE_UI_ACCESS_CODE"):
        raise RuntimeError("operator-controlled THREADEYE_EVIDENCE_UI_ACCESS_CODE is required")
    required["PYTHONDONTWRITEBYTECODE"] = "1"
    required["PYTHONPATH"] = str(project / "src")
    return required


def _mcp_child_environment(required: dict[str, str], config_path: Path, public_path: Path) -> dict[str, str]:
    child = dict(required)
    for name in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SSL_CERT_FILE", "SSL_CERT_DIR"):
        if os.environ.get(name):
            child[name] = os.environ[name]
    child["THREADEYE_EVIDENCE_HTTP_CONFIG"] = str(config_path)
    child["THREADEYE_EVIDENCE_HTTP_PUBLIC_KEY"] = str(public_path)
    return child


def _wait_ready(config: HTTPAuthorizationConfig, process: subprocess.Popen) -> None:
    metadata = config.resource_url.replace("/mcp", "/.well-known/oauth-protected-resource/mcp")
    for _ in range(80):
        if process.poll() is not None:
            raise RuntimeError("MCP server exited before becoming ready")
        try:
            if httpx2.get(metadata, timeout=0.5).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError("MCP server did not become ready")


def _terminate(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> int:
    project = Path(__file__).resolve().parents[3]
    process: subprocess.Popen | None = None
    try:
        environment = _required_environment(project)
        base_config_path = Path(os.environ.get("THREADEYE_EVIDENCE_HTTP_CONFIG", project / "config/mcp-http.json"))
        HTTPAuthorizationConfig.load(base_config_path)
        raw = json.loads(base_config_path.read_text(encoding="utf-8"))
        mcp_port = int(os.environ.get("THREADEYE_EVIDENCE_MCP_HTTP_PORT", raw["port"]))
        ui_port = int(os.environ.get("THREADEYE_EVIDENCE_UI_PORT", "8770"))
        raw["port"] = mcp_port
        raw["resource_url"] = f"http://127.0.0.1:{mcp_port}/mcp"
        raw["allowed_origins"] = [f"http://127.0.0.1:{mcp_port}"]
        ui_config = UIConfig(port=ui_port)
        if mcp_port == ui_port or not _port_available("127.0.0.1", mcp_port) or not _port_available("127.0.0.1", ui_port):
            raise RuntimeError("configured localhost port is unavailable")
        with tempfile.TemporaryDirectory(prefix="threadeye-judge-") as temporary:
            temporary_path = Path(temporary)
            config_path = temporary_path / "mcp-http.json"
            config_path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            config_path.chmod(0o600)
            private_key = Ed25519PrivateKey.generate()
            public_path = temporary_path / "mcp-public.pem"
            public_path.write_bytes(private_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))
            public_path.chmod(0o600)
            http_config = HTTPAuthorizationConfig.load(config_path)
            child_environment = _mcp_child_environment(environment, config_path, public_path)
            process = subprocess.Popen(
                [sys.executable, "-m", "threadeye_evidence.mcp.http_server"],
                cwd=project,
                env=child_environment,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
            )
            _wait_ready(http_config, process)
            gateway = MCPHTTPGateway(http_config, private_key)
            app = build_ui_app(gateway, os.environ["THREADEYE_EVIDENCE_UI_ACCESS_CODE"], config=ui_config)
            print(f"ThreadEye Evidence Assistant judge UI: {ui_config.origin}", file=sys.stderr)
            print("Use the operator-provided local access code. No MCP token is exposed to the browser.", file=sys.stderr)
            uvicorn.run(app, host=ui_config.host, port=ui_config.port, access_log=False, server_header=False, log_level="warning")
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"ThreadEye judge UI startup failed safely: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        _terminate(process)


if __name__ == "__main__":
    raise SystemExit(main())
