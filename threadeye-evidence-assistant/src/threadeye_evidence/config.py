"""Security-relevant inventory configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MAX_DOCUMENT_BYTES = 1_048_576
ALLOWED_SOURCE_EXTENSIONS = frozenset({".md"})


@dataclass(frozen=True)
class InventoryConfig:
    """Operator-owned paths; document selection still comes only from the manifest."""

    source_root: Path
    manifest_path: Path
    max_document_bytes: int = MAX_DOCUMENT_BYTES

    def __post_init__(self) -> None:
        if self.max_document_bytes <= 0:
            raise ValueError("max_document_bytes must be positive")
