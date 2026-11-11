"""Heading-aware, deterministic variable chunking with normalized source spans."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from typing import Any

PROCESSING_VERSION = "threadeye-chunk-v1"

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*(?:\n)?$")
_FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
_SENTENCE_BOUNDARY = re.compile(r"[.!?](?:[\"')\]]*)\s+")


@dataclass(frozen=True)
class ChunkConfig:
    target_chars: int = 800
    max_chars: int = 1200
    overlap_chars: int = 0

    def __post_init__(self) -> None:
        if self.target_chars < 100:
            raise ValueError("target_chars must be at least 100")
        if self.max_chars < self.target_chars:
            raise ValueError("max_chars must be greater than or equal to target_chars")
        if self.overlap_chars != 0:
            raise ValueError("Prompt 03 supports zero overlap only to prevent unintended duplication")


@dataclass(frozen=True)
class SectionSpan:
    start: int
    end: int
    heading_path: tuple[str, ...]


@dataclass(frozen=True)
class DocumentChunk:
    source_relative_path: str
    source_sha256: str
    chunk_id: str
    heading_path: tuple[str, ...]
    sanitization_status: str
    chunk_sha256: str
    position: int
    normalized_start: int
    normalized_end: int
    source_span_basis: str
    processing_version: str
    approval_reference: str
    size_chars: int
    overlap_chars: int
    content: str

    def to_mapping(self, *, include_content: bool = True) -> dict[str, Any]:
        result = asdict(self)
        result["heading_path"] = list(self.heading_path)
        if not include_content:
            result.pop("content")
        return result


def _sections(text: str) -> list[SectionSpan]:
    lines = text.splitlines(keepends=True)
    spans: list[SectionSpan] = []
    headings: list[str] = []
    section_start = 0
    section_headings: tuple[str, ...] = ()
    offset = 0
    in_fence = False
    fence_marker = ""

    for line in lines:
        fence = _FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not in_fence:
                in_fence = True
                fence_marker = marker[0]
            elif marker[0] == fence_marker:
                in_fence = False
                fence_marker = ""
        elif not in_fence:
            heading = _HEADING.match(line)
            if heading:
                if offset > section_start:
                    spans.append(SectionSpan(section_start, offset, section_headings))
                level = len(heading.group(1))
                title = heading.group(2).strip()
                headings = headings[: level - 1]
                headings.append(title)
                section_start = offset
                section_headings = tuple(headings)
        offset += len(line)

    if offset > section_start:
        spans.append(SectionSpan(section_start, offset, section_headings))
    if not spans and text:
        spans.append(SectionSpan(0, len(text), ()))
    return spans


def _candidate_boundaries(segment: str, start: int, max_end: int, pattern: re.Pattern[str]) -> list[int]:
    return [match.end() for match in pattern.finditer(segment, start, max_end)]


def _choose_boundary(segment: str, start: int, target: int, maximum: int) -> int:
    minimum = min(target, start + max(50, (target - start) // 2))
    boundary_patterns = (re.compile(r"\n\n"), _SENTENCE_BOUNDARY, re.compile(r"\n"))
    for pattern in boundary_patterns:
        candidates = [value for value in _candidate_boundaries(segment, start, maximum, pattern) if value > minimum]
        if not candidates:
            continue
        at_or_after_target = [value for value in candidates if value >= target]
        return at_or_after_target[0] if at_or_after_target else candidates[-1]
    return maximum


def _split_section(text: str, section: SectionSpan, config: ChunkConfig) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = section.start
    while start < section.end:
        remaining = section.end - start
        if remaining <= config.max_chars:
            end = section.end
        else:
            target = min(start + config.target_chars, section.end)
            maximum = min(start + config.max_chars, section.end)
            end = _choose_boundary(text, start, target, maximum)
        if end <= start:
            raise RuntimeError("chunker failed to advance")
        spans.append((start, end))
        start = end
    return spans


def chunk_markdown(
    text: str,
    *,
    source_relative_path: str,
    source_sha256: str,
    sanitization_status: str,
    approval_reference: str,
    config: ChunkConfig | None = None,
) -> list[DocumentChunk]:
    """Partition normalized Markdown by headings, then semantic boundaries for oversized sections."""

    active_config = config or ChunkConfig()
    chunks: list[DocumentChunk] = []
    for section in _sections(text):
        for start, end in _split_section(text, section, active_config):
            content = text[start:end]
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            identity = (
                f"{PROCESSING_VERSION}\0{source_relative_path}\0{source_sha256}\0{start}:{end}\0{content_hash}"
            )
            chunk_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            chunks.append(
                DocumentChunk(
                    source_relative_path,
                    source_sha256,
                    chunk_id,
                    section.heading_path,
                    sanitization_status,
                    content_hash,
                    len(chunks),
                    start,
                    end,
                    "sanitized_normalized_text_v1",
                    PROCESSING_VERSION,
                    approval_reference,
                    len(content),
                    active_config.overlap_chars,
                    content,
                )
            )
    return chunks
