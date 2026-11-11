"""Deterministic metadata-only inventory for manifest-approved documents."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from threadeye_evidence.config import MAX_DOCUMENT_BYTES
from threadeye_evidence.corpus.allowlist import Manifest
from threadeye_evidence.corpus.hashing import sha256_file
from threadeye_evidence.corpus.safety import SafetyViolation, resolve_source_file


@dataclass(frozen=True)
class InventoryRecord:
    relative_path: str
    purpose: str
    source_classification: str
    inventory_approved: bool
    future_ingestion_approved: bool
    caveats: str
    size_bytes: int | None
    sha256: str | None
    modified_at: str | None
    error: str | None

    def to_mapping(self) -> dict[str, Any]:
        return asdict(self)


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return "missing_file"
    if isinstance(exc, PermissionError):
        return "permission_denied"
    if isinstance(exc, SafetyViolation):
        return f"validation_error: {exc}"
    return f"inventory_error: {type(exc).__name__}"


def inventory_documents(
    source_root: Path,
    manifest: Manifest,
    *,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> list[InventoryRecord]:
    """Inventory approved entries only; do not recurse, copy contents, or write output files."""

    records: list[InventoryRecord] = []
    for entry in manifest.documents:
        if not entry.inventory_approved:
            records.append(
                InventoryRecord(
                    entry.path,
                    entry.purpose,
                    entry.source_classification,
                    False,
                    entry.future_ingestion_approved,
                    entry.caveats,
                    None,
                    None,
                    None,
                    "inventory_not_approved",
                )
            )
            continue
        try:
            manifest.require_approved(entry.path)
            source = resolve_source_file(source_root, entry.path, max_bytes=max_bytes)
            stat = source.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
            records.append(
                InventoryRecord(
                    entry.path,
                    entry.purpose,
                    entry.source_classification,
                    True,
                    entry.future_ingestion_approved,
                    entry.caveats,
                    stat.st_size,
                    sha256_file(source),
                    modified,
                    None,
                )
            )
        except (FileNotFoundError, PermissionError, SafetyViolation, OSError) as exc:
            records.append(
                InventoryRecord(
                    entry.path,
                    entry.purpose,
                    entry.source_classification,
                    True,
                    entry.future_ingestion_approved,
                    entry.caveats,
                    None,
                    None,
                    None,
                    _safe_error(exc),
                )
            )
    return records
