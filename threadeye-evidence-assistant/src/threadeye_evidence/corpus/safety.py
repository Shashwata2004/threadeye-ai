"""Path and file controls for approved source documents."""

from __future__ import annotations

import os
from pathlib import Path, PurePosixPath

from threadeye_evidence.config import ALLOWED_SOURCE_EXTENSIONS, MAX_DOCUMENT_BYTES


class SafetyViolation(ValueError):
    """A manifest path or source file violates the read-only evidence contract."""


_FORBIDDEN_NAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.cloud",
        "credentials",
        "credentials.json",
        "secrets",
        "secrets.json",
        "id_rsa",
        "id_ed25519",
    }
)
_FORBIDDEN_SUFFIXES = frozenset({".key", ".pem", ".p12", ".pfx", ".sql", ".dump", ".bak", ".sqlite", ".db"})


def validate_relative_path(value: str) -> PurePosixPath:
    """Validate one manifest path without touching the filesystem."""

    if not isinstance(value, str) or not value.strip():
        raise SafetyViolation("manifest path must be a non-empty string")
    if "\\" in value:
        raise SafetyViolation("manifest paths must use forward slashes")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise SafetyViolation("absolute manifest paths are forbidden")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise SafetyViolation("path traversal or ambiguous path segments are forbidden")
    if any(part.startswith(".") for part in path.parts):
        raise SafetyViolation("hidden files and directories are forbidden")
    basename = path.name.lower()
    suffix = path.suffix.lower()
    if basename in _FORBIDDEN_NAMES or basename.startswith(".env"):
        raise SafetyViolation("environment or credential files are forbidden")
    if suffix in _FORBIDDEN_SUFFIXES:
        raise SafetyViolation("credential and database file formats are forbidden")
    if suffix not in ALLOWED_SOURCE_EXTENSIONS:
        raise SafetyViolation(f"unapproved source extension: {suffix or '<none>'}")
    return path


def resolve_source_file(
    source_root: Path,
    relative_path: str,
    *,
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> Path:
    """Resolve and validate an existing approved file below ``source_root``."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    manifest_path = validate_relative_path(relative_path)
    root = source_root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise SafetyViolation("source root is not a directory")
    candidate = root.joinpath(*manifest_path.parts)

    # Refuse all symlinks, including safe-looking in-root links, to keep the contract simple and stable.
    current = root
    for part in manifest_path.parts:
        current = current / part
        if current.is_symlink():
            raise SafetyViolation("symlink source entries are forbidden")

    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SafetyViolation("resolved source path escapes the approved root") from exc
    if not resolved.is_file():
        raise SafetyViolation("source entry is not a regular file")
    stat = resolved.stat()
    if not os.path.isfile(resolved):
        raise SafetyViolation("source entry is not a regular file")
    if stat.st_size > max_bytes:
        raise SafetyViolation(f"source file exceeds the {max_bytes}-byte limit")
    return resolved


def forbidden_source_name(value: str) -> bool:
    """Return whether a path is an explicitly forbidden secret/database form."""

    try:
        validate_relative_path(value)
    except SafetyViolation:
        return True
    return False
