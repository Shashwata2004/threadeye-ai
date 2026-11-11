"""Manifest loading and exact allowlist enforcement."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from threadeye_evidence.corpus.safety import SafetyViolation, validate_relative_path


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    purpose: str
    source_classification: str
    inventory_approved: bool
    future_ingestion_approved: bool = False
    caveats: str = ""

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "ManifestEntry":
        required = {"path", "purpose", "source_classification", "inventory_approved"}
        missing = required - raw.keys()
        if missing:
            raise ValueError(f"manifest entry missing fields: {', '.join(sorted(missing))}")
        path = str(validate_relative_path(raw["path"]))
        purpose = raw["purpose"]
        classification = raw["source_classification"]
        approved = raw["inventory_approved"]
        future = raw.get("future_ingestion_approved", False)
        caveats = raw.get("caveats", "")
        if not isinstance(purpose, str) or not purpose.strip():
            raise ValueError("manifest purpose must be a non-empty string")
        if not isinstance(classification, str) or not classification.strip():
            raise ValueError("source_classification must be a non-empty string")
        if not isinstance(approved, bool) or not isinstance(future, bool):
            raise ValueError("approval fields must be boolean")
        if not isinstance(caveats, str):
            raise ValueError("caveats must be a string")
        if future and not approved:
            raise ValueError("future ingestion cannot be approved when inventory is not approved")
        return cls(path, purpose.strip(), classification.strip(), approved, future, caveats.strip())


@dataclass(frozen=True)
class Manifest:
    version: int
    source_project: str
    documents: tuple[ManifestEntry, ...]

    @property
    def approved_paths(self) -> frozenset[str]:
        return frozenset(entry.path for entry in self.documents if entry.inventory_approved)

    def require_approved(self, relative_path: str) -> ManifestEntry:
        normalized = str(validate_relative_path(relative_path))
        for entry in self.documents:
            if entry.path == normalized and entry.inventory_approved:
                return entry
        raise SafetyViolation("source path is not approved by the manifest")


def load_manifest(path: Path) -> Manifest:
    """Load a local companion manifest; document contents are never loaded here."""

    with path.open("r", encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise ValueError("manifest root must be an object")
    if raw.get("version") != 1:
        raise ValueError("unsupported manifest version")
    source_project = raw.get("source_project")
    documents = raw.get("documents")
    if not isinstance(source_project, str) or not source_project.strip():
        raise ValueError("source_project must be a non-empty string")
    if not isinstance(documents, list) or not documents:
        raise ValueError("manifest documents must be a non-empty list")
    entries = tuple(ManifestEntry.from_mapping(item) for item in documents if isinstance(item, dict))
    if len(entries) != len(documents):
        raise ValueError("every document entry must be an object")
    paths = [entry.path for entry in entries]
    if len(paths) != len(set(paths)):
        raise ValueError("manifest contains duplicate paths")
    return Manifest(1, source_project.strip(), entries)
