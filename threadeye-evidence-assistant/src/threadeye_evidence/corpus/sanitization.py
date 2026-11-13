"""Conservative redaction for untrusted Markdown before any content is persisted."""

from __future__ import annotations

import re
from dataclasses import dataclass


class SanitizationRejected(ValueError):
    """High-risk content requires manual review instead of automatic publication."""


@dataclass(frozen=True)
class SanitizationFinding:
    kind: str
    action: str


@dataclass(frozen=True)
class SanitizationResult:
    text: str
    findings: tuple[SanitizationFinding, ...]

    @property
    def status(self) -> str:
        return "redacted" if self.findings else "clean"


_PRIVATE_KEY = re.compile(r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----", re.IGNORECASE)

_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "database_url",
        re.compile(r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis)://[^\s<>()]+", re.IGNORECASE),
        "[REDACTED_DATABASE_URL]",
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
        "Bearer [REDACTED_TOKEN]",
    ),
    (
        "known_token",
        re.compile(r"\b(?:sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})\b"),
        "[REDACTED_TOKEN]",
    ),
    (
        "credential_assignment",
        re.compile(
            r"(?im)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|pwd|secret)\b"
            r"\s*[:=]\s*)(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s#,\n]+)"
        ),
        r"\1[REDACTED_CREDENTIAL]",
    ),
    (
        "email",
        re.compile(r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.IGNORECASE),
        "[REDACTED_EMAIL]",
    ),
    (
        "private_url",
        re.compile(
            r"https?://(?:localhost|127(?:\.\d{1,3}){3}|10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
            r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|[A-Za-z0-9.-]+\.internal)"
            r"(?::\d{1,5})?(?:/[^\s<>()]*)?",
            re.IGNORECASE,
        ),
        "[REDACTED_PRIVATE_URL]",
    ),
    (
        "private_identifier",
        re.compile(
            r"(?im)(\b(?:customer|factory|buyer|mill|inspection)[_-]?id\s*[:=]\s*)"
            r"(?:\"[^\"\n]*\"|'[^'\n]*'|[^\s#,\n]+)"
        ),
        r"\1[REDACTED_IDENTIFIER]",
    ),
)


def sanitize_markdown(text: str) -> SanitizationResult:
    """Redact supported sensitive patterns; fail closed for private-key material."""

    if _PRIVATE_KEY.search(text):
        raise SanitizationRejected("high-risk private-key material requires manual review")
    sanitized = text
    findings: list[SanitizationFinding] = []
    for kind, pattern, replacement in _PATTERNS:
        sanitized, count = pattern.subn(replacement, sanitized)
        findings.extend(SanitizationFinding(kind, "redacted") for _ in range(count))
    return SanitizationResult(sanitized, tuple(findings))
