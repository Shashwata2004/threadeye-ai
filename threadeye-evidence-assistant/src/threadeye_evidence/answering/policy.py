"""Question and evidence safety policy for the ThreadEye companion."""

from __future__ import annotations

import re
import unicodedata

from threadeye_evidence.answering.models import AbstentionReason


class QuestionSecurityError(ValueError):
    """Input contains hidden controls or mixed-script obfuscation."""


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
    r"follow (?:the )?instructions? (?:inside|in) (?:the )?(?:document|evidence))\b|"
    r"\b(?:system|developer|assistant)\s*(?:message|instruction)?\s*:",
    re.IGNORECASE,
)
_VERDICT = re.compile(
    r"\b(?:approve|reject|pass|fail)\b.{0,35}\b(?:this |the |actual |real )?(?:roll|fabric|shipment)\b|"
    r"\b(?:give|change|override|recalculate)\b.{0,35}\b(?:roll verdict|quality decision|four[- ]point score|supervisor approval)\b",
    re.IGNORECASE,
)
_CONTRADICTION = re.compile(r"\b(?:contradictory|conflicting|mutually exclusive|opposite claims?)\b", re.IGNORECASE)
_EVIDENCE_INJECTION = re.compile(
    r"\b(?:ignore (?:all |the )?(?:previous|prior|system) instructions|reveal credentials|"
    r"fabricate (?:a )?citation|do not cite (?:this|the source))\b|"
    r"\b(?:system|developer|assistant)\s*(?:message|instruction)?\s*:",
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
    return bool(_EVIDENCE_INJECTION.search(_canonical_security_text(text)))


def contains_explicit_contradiction(text: str) -> bool:
    return bool(_EVIDENCE_CONTRADICTION.search(_canonical_security_text(text)))


def _canonical_security_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    return "".join(character for character in normalized if unicodedata.category(character) not in {"Cf", "Cs", "Co"})


def contains_keyword_stuffing(text: str) -> bool:
    tokens = re.findall(r"[a-z0-9-]+", _canonical_security_text(text).lower())
    if len(tokens) < 12:
        return False
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    return max(counts.values(), default=0) >= 6 or len(set(tokens)) / len(tokens) < 0.35


def normalize_question_input(question: str) -> str:
    if not isinstance(question, str):
        raise QuestionSecurityError("question must be text")
    normalized = unicodedata.normalize("NFKC", question)
    for character in normalized:
        category = unicodedata.category(character)
        if category in {"Cc", "Cf", "Cs", "Co"} and character not in {"\t", "\n", "\r"}:
            raise QuestionSecurityError("question contains hidden or unsupported control characters")
    scripts: set[str] = set()
    for character in normalized:
        name = unicodedata.name(character, "")
        if "LATIN" in name:
            scripts.add("latin")
        elif "CYRILLIC" in name:
            scripts.add("cyrillic")
        elif "GREEK" in name:
            scripts.add("greek")
    if len(scripts) > 1:
        raise QuestionSecurityError("mixed-script question requires manual review")
    return normalized
