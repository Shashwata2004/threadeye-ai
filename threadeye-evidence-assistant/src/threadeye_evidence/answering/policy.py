"""Question and evidence safety policy for the ThreadEye companion."""

from __future__ import annotations

import re

from threadeye_evidence.answering.models import AbstentionReason


_SECRET = re.compile(
    r"\b(?:reveal|show|print|extract|give|leak)\b.{0,50}\b(?:password|credential|secret|token|api[_ -]?key|private data)\b",
    re.IGNORECASE,
)
_PRODUCTION = re.compile(
    r"\b(?:connect|query|access|dump|read|write|modify)\b.{0,40}\b(?:production|supabase|customer database|factory database)\b",
    re.IGNORECASE,
)
_INJECTION = re.compile(
    r"\b(?:ignore (?:all |the )?(?:previous|prior|system) instructions|reveal (?:the )?(?:hidden|system) prompt|"
    r"follow (?:the )?instructions? (?:inside|in) (?:the )?(?:document|evidence))\b",
    re.IGNORECASE,
)
_VERDICT = re.compile(
    r"\b(?:approve|reject|pass|fail)\b.{0,35}\b(?:this |the |actual |real )?(?:roll|fabric|shipment)\b|"
    r"\b(?:give|change|override|recalculate)\b.{0,35}\b(?:roll verdict|quality decision|four[- ]point score|supervisor approval)\b",
    re.IGNORECASE,
)
_CONTRADICTION = re.compile(r"\b(?:contradictory|conflicting|mutually exclusive|opposite claims?)\b", re.IGNORECASE)
_EVIDENCE_INJECTION = re.compile(
    r"\b(?:ignore (?:all |the )?(?:previous|prior|system) instructions|reveal credentials|system message:)\b",
    re.IGNORECASE,
)
_EVIDENCE_CONTRADICTION = re.compile(
    r"\b(?:conflicts? with|contradicts?|mutually exclusive|opposite claims?|inconsistent notes?)\b",
    re.IGNORECASE,
)


def rejected_request_reason(question: str) -> str | None:
    if _SECRET.search(question):
        return AbstentionReason.SECRET_EXFILTRATION_REQUEST.value
    if _PRODUCTION.search(question):
        return AbstentionReason.PRODUCTION_ACCESS_REQUEST.value
    if _INJECTION.search(question):
        return AbstentionReason.PROMPT_INJECTION_REQUEST.value
    if _VERDICT.search(question):
        return AbstentionReason.VERDICT_OVERRIDE_REQUEST.value
    if _CONTRADICTION.search(question):
        return AbstentionReason.CONTRADICTORY_EVIDENCE.value
    return None


def contains_untrusted_instruction(text: str) -> bool:
    return bool(_EVIDENCE_INJECTION.search(text))


def contains_explicit_contradiction(text: str) -> bool:
    return bool(_EVIDENCE_CONTRADICTION.search(text))
