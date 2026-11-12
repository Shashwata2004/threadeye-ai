"""Trusted operator-controlled authorization context for the stdio MCP server."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from threadeye_evidence.corpus.safety import validate_relative_path
from threadeye_evidence.retrieval.models import RetrievalFilters
from threadeye_evidence.vector.embeddings import EmbeddingMetadata


class AuthorizationConfigurationError(ValueError):
    """The trusted startup context is missing, unsafe, or inconsistent."""


_REQUIRED_KEYS = frozenset({
    "version", "corpus_id", "access_policy", "authorization_reference",
    "document_classification", "embedding_profile_key", "allowed_source",
    "source_description", "max_query_chars", "max_top_k", "max_response_bytes",
    "tool_timeout_seconds", "max_concurrency",
})


@dataclass(frozen=True)
class TrustedAuthorizationContext:
    version: int
    corpus_id: str
    access_policy: str
    authorization_reference: str
    document_classification: str
    embedding_profile_key: str
    allowed_source: str
    source_description: str
    max_query_chars: int
    max_top_k: int
    max_response_bytes: int
    tool_timeout_seconds: float
    max_concurrency: int
    config_path: Path

    @classmethod
    def load(cls, path: Path) -> "TrustedAuthorizationContext":
        value = Path(path)
        if value.is_symlink():
            raise AuthorizationConfigurationError("trusted authorization configuration cannot be a symlink")
        try:
            metadata = value.stat()
        except OSError as exc:
            raise AuthorizationConfigurationError("trusted authorization configuration is unavailable") from exc
        if not stat.S_ISREG(metadata.st_mode):
            raise AuthorizationConfigurationError("trusted authorization configuration must be a regular file")
        if metadata.st_mode & (stat.S_IWGRP | stat.S_IWOTH):
            raise AuthorizationConfigurationError("trusted authorization configuration is broadly writable")
        if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
            raise AuthorizationConfigurationError("trusted authorization configuration has an unexpected owner")
        try:
            raw = json.loads(value.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuthorizationConfigurationError("trusted authorization configuration is invalid") from exc
        if not isinstance(raw, dict) or set(raw) != _REQUIRED_KEYS:
            raise AuthorizationConfigurationError("trusted authorization configuration fields are invalid")
        for name in (
            "corpus_id", "access_policy", "authorization_reference", "document_classification",
            "embedding_profile_key", "allowed_source", "source_description",
        ):
            if not isinstance(raw[name], str) or not raw[name].strip():
                raise AuthorizationConfigurationError(f"{name} must be a non-empty string")
        validate_relative_path(raw["allowed_source"])
        if raw["version"] != 1:
            raise AuthorizationConfigurationError("trusted authorization configuration version is unsupported")
        if not 1 <= raw["max_top_k"] <= 10:
            raise AuthorizationConfigurationError("max_top_k must be from 1 through 10")
        if not 1 <= raw["max_query_chars"] <= 1_000:
            raise AuthorizationConfigurationError("max_query_chars must be from 1 through 1000")
        if not 4_096 <= raw["max_response_bytes"] <= 262_144:
            raise AuthorizationConfigurationError("max_response_bytes is outside the safe range")
        if not 1.0 <= raw["tool_timeout_seconds"] <= 30.0:
            raise AuthorizationConfigurationError("tool_timeout_seconds is outside the safe range")
        if not 1 <= raw["max_concurrency"] <= 16:
            raise AuthorizationConfigurationError("max_concurrency is outside the safe range")
        return cls(**raw, config_path=value.resolve())

    @classmethod
    def from_environment(cls) -> "TrustedAuthorizationContext":
        path = os.environ.get("THREADEYE_EVIDENCE_MCP_CONFIG")
        if not path:
            raise AuthorizationConfigurationError("trusted MCP authorization context is missing")
        return cls.load(Path(path))

    def filters(self) -> RetrievalFilters:
        return RetrievalFilters(
            self.corpus_id,
            self.access_policy,
            self.authorization_reference,
            source_relative_path=self.allowed_source,
            document_classification=self.document_classification,
        )

    def validate_embedding_profile(self, metadata: EmbeddingMetadata) -> None:
        if metadata.profile_key != self.embedding_profile_key:
            raise AuthorizationConfigurationError("configured embedding profile does not match the pinned provider")

    def public_mapping(self) -> dict[str, Any]:
        return {
            "authorization_context_version": self.version,
            "corpus_id": self.corpus_id,
            "access_policy": self.access_policy,
            "document_classification": self.document_classification,
            "allowed_source": self.allowed_source,
            "limits": {
                "max_query_chars": self.max_query_chars,
                "max_top_k": self.max_top_k,
                "max_response_bytes": self.max_response_bytes,
                "tool_timeout_seconds": self.tool_timeout_seconds,
                "max_concurrency": self.max_concurrency,
            },
        }
