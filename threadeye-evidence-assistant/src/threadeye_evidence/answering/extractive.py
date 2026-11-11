"""Deterministic sentence extraction; this is not an LLM generator."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from threadeye_evidence.answering.abstention import content_tokens
from threadeye_evidence.answering.policy import contains_untrusted_instruction
from threadeye_evidence.retrieval.models import RankedEvidence


_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class ExtractedSupport:
    ranked_evidence: RankedEvidence
    excerpt: str


@dataclass(frozen=True)
class ExtractiveOutput:
    answer: str
    supports: tuple[ExtractedSupport, ...]


class ExtractiveAnswerProvider:
    answer_mode = "extractive"

    def build(self, question: str, results: Sequence[RankedEvidence], *, max_sentences: int = 2) -> ExtractiveOutput:
        if not results:
            raise ValueError("extractive answers require retrieved evidence")
        query_tokens = content_tokens(question)
        ranked = results[0]
        candidates: list[tuple[int, int, str]] = []
        for position, raw in enumerate(_SENTENCE.split(ranked.candidate.sanitized_text)):
            if raw.strip().startswith("#"):
                continue
            sentence = raw.strip()
            if not sentence or len(sentence) < 12 or contains_untrusted_instruction(sentence):
                continue
            overlap = len(query_tokens & content_tokens(sentence))
            candidates.append((overlap, -position, sentence))
        if not candidates:
            raise ValueError("no safe extractive statement is available")
        candidates.sort(reverse=True)
        selected = [candidates[0][2]]
        selected.extend(sentence for overlap, _, sentence in candidates[1:] if overlap > 0)
        selected = selected[:max_sentences]
        selected.sort(key=lambda sentence: ranked.candidate.sanitized_text.find(sentence))
        supports = tuple(ExtractedSupport(ranked, sentence) for sentence in selected)
        return ExtractiveOutput(" ".join(selected), supports)
