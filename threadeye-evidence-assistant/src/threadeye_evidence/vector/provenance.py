"""Fail-closed validation for sanitized Prompt 03 ingestion results."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from threadeye_evidence.corpus.chunking import DocumentChunk
from threadeye_evidence.corpus.ingestion import IngestionResult
from threadeye_evidence.corpus.sanitization import SanitizationRejected, sanitize_markdown

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHUNK_ID = re.compile(r"^[0-9a-f]{24}$")


class ProvenanceValidationError(ValueError):
    """A record is not demonstrably approved, sanitized, and internally consistent."""


@dataclass(frozen=True)
class ApprovedChunkBatch:
    source_relative_path: str
    source_sha256: str
    normalized_sha256: str
    approval_reference: str
    intended_use: str
    processing_version: str
    chunks: tuple[DocumentChunk, ...]


def approved_chunk_batch(result: IngestionResult) -> ApprovedChunkBatch:
    """Validate a sealed ingestion result; arbitrary source paths are never accepted here."""

    if not result.approval_reference.strip() or not result.intended_use.strip():
        raise ProvenanceValidationError("ingestion authorization provenance is incomplete")
    if not _SHA256.fullmatch(result.source_sha256) or not _SHA256.fullmatch(result.normalized_sha256):
        raise ProvenanceValidationError("ingestion hashes are invalid")
    if result.sanitization_status not in {"clean", "redacted"}:
        raise ProvenanceValidationError("sanitization status is invalid")
    if not result.chunks:
        raise ProvenanceValidationError("no sanitized chunks were provided")
    if hashlib.sha256(result.normalized_text.encode("utf-8")).hexdigest() != result.normalized_sha256:
        raise ProvenanceValidationError("normalized content hash mismatch")

    seen: set[str] = set()
    expected_start = 0
    reconstructed: list[str] = []
    for position, chunk in enumerate(result.chunks):
        if chunk.chunk_id in seen:
            raise ProvenanceValidationError("duplicate chunk identifier")
        seen.add(chunk.chunk_id)
        if not _CHUNK_ID.fullmatch(chunk.chunk_id):
            raise ProvenanceValidationError("chunk identifier is invalid")
        if chunk.position != position or chunk.normalized_start != expected_start:
            raise ProvenanceValidationError("chunk ordering or normalized span is invalid")
        if chunk.normalized_end - chunk.normalized_start != len(chunk.content):
            raise ProvenanceValidationError("chunk span does not match sanitized content")
        if not chunk.content.strip():
            raise ProvenanceValidationError("empty chunks cannot be indexed")
        if hashlib.sha256(chunk.content.encode("utf-8")).hexdigest() != chunk.chunk_sha256:
            raise ProvenanceValidationError("chunk content hash mismatch")
        expected_values = (
            chunk.source_relative_path == result.source_relative_path,
            chunk.source_sha256 == result.source_sha256,
            chunk.sanitization_status == result.sanitization_status,
            chunk.approval_reference == result.approval_reference,
            chunk.processing_version == result.processing_version,
            chunk.source_span_basis == "sanitized_normalized_text_v1",
        )
        if not all(expected_values):
            raise ProvenanceValidationError("chunk provenance does not match its ingestion result")
        try:
            second_pass = sanitize_markdown(chunk.content)
        except SanitizationRejected as exc:
            raise ProvenanceValidationError("chunk failed the sanitization safety regression") from exc
        if second_pass.text != chunk.content:
            raise ProvenanceValidationError("chunk is not fully sanitized")
        reconstructed.append(chunk.content)
        expected_start = chunk.normalized_end

    if "".join(reconstructed) != result.normalized_text:
        raise ProvenanceValidationError("chunk coverage does not reconstruct sanitized content")
    return ApprovedChunkBatch(
        result.source_relative_path,
        result.source_sha256,
        result.normalized_sha256,
        result.approval_reference,
        result.intended_use,
        result.processing_version,
        tuple(result.chunks),
    )
