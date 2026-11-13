"""Manifest loading and exact allowlist enforcement."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from threadeye_evidence.corpus.safety import SafetyViolation, validate_relative_path

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class IngestionAuthorizationError(SafetyViolation):
    """The document lacks one of the independent ingestion approvals."""


@dataclass(frozen=True)
class TeamAuthorization:
    reference: str
    intended_use: str
    approved_by: str
    scope: str

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> "TeamAuthorization":
        values: dict[str, str] = {}
        for field in ("reference", "intended_use", "approved_by", "scope"):
            value = raw.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"team_authorization.{field} must be a non-empty string")
            values[field] = value.strip()
        return cls(**values)


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    purpose: str
    source_classification: str
    inventory_approved: bool
    future_ingestion_approved: bool = False
    caveats: str = ""
    team_authorization: TeamAuthorization | None = None
    expected_sha256: str | None = None

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
        authorization_raw = raw.get("team_authorization")
        expected_sha256 = raw.get("expected_sha256")
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
        authorization = None
        if authorization_raw is not None:
            if not isinstance(authorization_raw, dict):
                raise ValueError("team_authorization must be an object")
            authorization = TeamAuthorization.from_mapping(authorization_raw)
        if expected_sha256 is not None:
            if not isinstance(expected_sha256, str) or not _SHA256_RE.fullmatch(expected_sha256):
                raise ValueError("expected_sha256 must be a lowercase 64-character SHA-256 digest")
        return cls(
            path,
            purpose.strip(),
            classification.strip(),
            approved,
            future,
            caveats.strip(),
            authorization,
            expected_sha256,
        )


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

    def require_ingestion_authorized(self, relative_path: str, intended_use: str) -> ManifestEntry:
        """Require inventory approval, ingestion approval, and matching documented team authorization."""

        try:
            entry = self.require_approved(relative_path)
        except SafetyViolation as exc:
            raise IngestionAuthorizationError("document is not approved for inventory or ingestion") from exc
        if not entry.future_ingestion_approved:
            raise IngestionAuthorizationError("document is not approved for content ingestion")
        authorization = entry.team_authorization
        if authorization is None:
            raise IngestionAuthorizationError("document has no documented team authorization")
        if not intended_use.strip() or authorization.intended_use != intended_use.strip():
            raise IngestionAuthorizationError("team authorization does not cover the requested intended use")
        return entry


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
