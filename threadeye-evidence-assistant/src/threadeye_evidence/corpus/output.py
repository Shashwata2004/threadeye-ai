"""Deterministic storage for sanitized synthetic snapshots only."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from threadeye_evidence.corpus.ingestion import IngestionResult
from threadeye_evidence.corpus.safety import SafetyViolation


def _safe_name(relative_path: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", relative_path.lower()).strip("-") or "document"


def write_sanitized_snapshot(result: IngestionResult, project_root: Path) -> Path:
    """Write only sanitized content beneath the companion's ignored build directory."""

    root = project_root.resolve(strict=True)
    output_dir = root / "build" / "sanitized"
    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_output = output_dir.resolve(strict=True)
    try:
        resolved_output.relative_to(root)
    except ValueError as exc:
        raise SafetyViolation("sanitized output directory escapes the companion project") from exc
    filename = f"{_safe_name(result.source_relative_path)}-{result.source_sha256[:12]}-v1.json"
    destination = resolved_output / filename
    payload = result.to_mapping(include_content=True)
    encoded = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(prefix=".snapshot-", suffix=".tmp", dir=str(resolved_output))
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination
