"""Approval-gated ingestion pipeline for untrusted Markdown documents."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from threadeye_evidence.config import MAX_DOCUMENT_BYTES
from threadeye_evidence.corpus.allowlist import Manifest
from threadeye_evidence.corpus.chunking import ChunkConfig, DocumentChunk, PROCESSING_VERSION, chunk_markdown
from threadeye_evidence.corpus.hashing import sha256_file
from threadeye_evidence.corpus.normalization import normalize_markdown
from threadeye_evidence.corpus.safety import SafetyViolation, resolve_source_file
from threadeye_evidence.corpus.sanitization import SanitizationFinding, sanitize_markdown


class IngestionError(ValueError):
    """A safe, non-content-bearing ingestion failure."""


@dataclass(frozen=True)
class IngestionResult:
    source_relative_path: str
    source_sha256: str
    normalized_sha256: str
    sanitization_status: str
    findings: tuple[SanitizationFinding, ...]
    approval_reference: str
    intended_use: str
    processing_version: str
    normalized_text: str
    chunks: tuple[DocumentChunk, ...]

    def to_mapping(self, *, include_content: bool = False) -> dict[str, Any]:
        findings_by_kind: dict[str, int] = {}
        for finding in self.findings:
            findings_by_kind[finding.kind] = findings_by_kind.get(finding.kind, 0) + 1
        result: dict[str, Any] = {
            "source_relative_path": self.source_relative_path,
            "source_sha256": self.source_sha256,
            "normalized_sha256": self.normalized_sha256,
            "sanitization_status": self.sanitization_status,
            "redaction_counts": findings_by_kind,
            "approval_reference": self.approval_reference,
            "intended_use": self.intended_use,
            "processing_version": self.processing_version,
            "normalized_size_chars": len(self.normalized_text),
            "chunk_count": len(self.chunks),
            "chunks": [chunk.to_mapping(include_content=include_content) for chunk in self.chunks],
        }
        if include_content:
            result["normalized_text"] = self.normalized_text
        return result


def ingest_document(
    source_root: Path,
    manifest: Manifest,
    relative_path: str,
    *,
    intended_use: str,
    chunk_config: ChunkConfig | None = None,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> IngestionResult:
    """Authorize, validate, hash, sanitize, normalize, and chunk one exact manifest document."""

    entry = manifest.require_ingestion_authorized(relative_path, intended_use)
    authorization = entry.team_authorization
    if authorization is None:  # Defensive: the manifest gate above already checks this.
        raise IngestionError("document authorization is incomplete")

    source = resolve_source_file(source_root, entry.path, max_bytes=max_bytes)
    before_hash = sha256_file(source)
    try:
        with source.open("rb") as handle:
            raw_bytes = handle.read(max_bytes + 1)
    except OSError as exc:
        raise IngestionError("source document could not be read") from exc
    if len(raw_bytes) > max_bytes:
        raise SafetyViolation("source document exceeded the size limit during ingestion")
    bytes_hash = hashlib.sha256(raw_bytes).hexdigest()
    after_hash = sha256_file(source)
    if before_hash != bytes_hash or after_hash != bytes_hash:
        raise IngestionError("source document changed during ingestion")
    if entry.expected_sha256 is not None and entry.expected_sha256 != bytes_hash:
        raise IngestionError("source document hash does not match the approved manifest")
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise SafetyViolation("source document is not valid UTF-8 Markdown") from exc

    sanitized = sanitize_markdown(raw_text)
    normalized = normalize_markdown(sanitized.text)
    normalized_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    chunks = chunk_markdown(
        normalized,
        source_relative_path=entry.path,
        source_sha256=bytes_hash,
        sanitization_status=sanitized.status,
        approval_reference=authorization.reference,
        config=chunk_config,
    )
    if "".join(chunk.content for chunk in chunks) != normalized:
        raise IngestionError("chunk coverage verification failed")
    return IngestionResult(
        entry.path,
        bytes_hash,
        normalized_hash,
        sanitized.status,
        sanitized.findings,
        authorization.reference,
        intended_use,
        PROCESSING_VERSION,
        normalized,
        tuple(chunks),
    )
