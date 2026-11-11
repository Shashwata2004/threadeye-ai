"""Answer-provider contracts; Prompt 06 implements extraction, not LLM generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


@dataclass(frozen=True)
class GeneratorMetadata:
    provider_name: str
    model_identity: str
    max_context_chars: int
    timeout_seconds: float
    capability: str
    available: bool


@dataclass(frozen=True)
class GenerationRequest:
    question: str
    contexts: tuple[dict[str, Any], ...]
    max_output_tokens: int
    temperature: float


@dataclass(frozen=True)
class GenerationResult:
    answer: str
    cited_chunk_ids: tuple[str, ...]
    provider_metadata: GeneratorMetadata


class GeneratorProvider(Protocol):
    @property
    def metadata(self) -> GeneratorMetadata: ...

    def generate(self, request: GenerationRequest) -> GenerationResult: ...


class UnavailableGeneratorProvider:
    """Explicit future interface; never masquerades as a working generator."""

    metadata = GeneratorMetadata(
        provider_name="not-implemented",
        model_identity="none",
        max_context_chars=0,
        timeout_seconds=0.0,
        capability="future_llm_generator",
        available=False,
    )

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise NotImplementedError("LLM answer generation is not implemented or verified in Prompt 06")
