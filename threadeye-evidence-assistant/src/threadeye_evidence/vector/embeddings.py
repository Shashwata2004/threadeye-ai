"""Versioned embedding-provider contract with a genuine local FastEmbed implementation."""

from __future__ import annotations

import hashlib
import math
import platform
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from importlib import metadata as package_metadata
from pathlib import Path
from typing import Any, Sequence

BGE_MODEL_ID = "BAAI/bge-small-en-v1.5"
BGE_MODEL_SOURCE = "Qdrant/bge-small-en-v1.5-onnx-Q"
BGE_MODEL_REVISION = "aa8f8b060edb00e03bfdd08813a2949946c8ba55"
BGE_DIMENSIONS = 384
MAX_EMBEDDING_INPUT_CHARS = 20_000


class EmbeddingValidationError(ValueError):
    """Embedding input, metadata, or output is invalid."""


@dataclass(frozen=True)
class EmbeddingMetadata:
    provider_id: str
    model_id: str
    model_revision: str
    dimensions: int
    distance_metric: str = "cosine"
    text_encoding: str = "utf-8"

    def __post_init__(self) -> None:
        for field_name in ("provider_id", "model_id", "model_revision"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise EmbeddingValidationError(f"{field_name} must be a non-empty string")
        if self.dimensions <= 0:
            raise EmbeddingValidationError("dimensions must be positive")
        if self.distance_metric != "cosine":
            raise EmbeddingValidationError("only cosine distance is supported")
        if self.text_encoding.lower() != "utf-8":
            raise EmbeddingValidationError("only UTF-8 text encoding is supported")

    @property
    def profile_key(self) -> str:
        identity = "\0".join(
            (
                self.provider_id,
                self.model_id,
                self.model_revision,
                str(self.dimensions),
                self.distance_metric,
                self.text_encoding,
            )
        )
        return hashlib.sha256(identity.encode("utf-8")).hexdigest()

    def to_mapping(self) -> dict[str, Any]:
        result = asdict(self)
        result["profile_key"] = self.profile_key
        return result


def validate_texts(texts: Sequence[str], *, batch_size: int) -> tuple[str, ...]:
    if isinstance(texts, (str, bytes)) or not isinstance(texts, Sequence):
        raise EmbeddingValidationError("texts must be a sequence of strings")
    if not texts:
        raise EmbeddingValidationError("at least one text is required")
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= 256:
        raise EmbeddingValidationError("batch_size must be an integer from 1 through 256")
    validated: list[str] = []
    for text in texts:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingValidationError("embedding inputs must be non-empty strings")
        if len(text) > MAX_EMBEDDING_INPUT_CHARS:
            raise EmbeddingValidationError("embedding input exceeds the character limit")
        text.encode("utf-8", errors="strict")
        validated.append(text)
    return tuple(validated)


def validate_vectors(vectors: Sequence[Sequence[float]], *, count: int, dimensions: int) -> list[list[float]]:
    if len(vectors) != count:
        raise EmbeddingValidationError("embedding provider returned an unexpected vector count")
    validated: list[list[float]] = []
    for vector in vectors:
        if len(vector) != dimensions:
            raise EmbeddingValidationError("embedding provider returned an unexpected dimension")
        values: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise EmbeddingValidationError("embedding contains a non-numeric value")
            numeric = float(value)
            if not math.isfinite(numeric):
                raise EmbeddingValidationError("embedding contains NaN or infinity")
            values.append(numeric)
        validated.append(values)
    return validated


class EmbeddingProvider(ABC):
    """Contract shared by real and test-only embedding providers."""

    @property
    @abstractmethod
    def metadata(self) -> EmbeddingMetadata:
        raise NotImplementedError

    @abstractmethod
    def embed_documents(self, texts: Sequence[str], *, batch_size: int = 32) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents((text,), batch_size=1)[0]

    def runtime_info(self) -> dict[str, Any]:
        return {"python": platform.python_version(), "platform": platform.platform()}


class FastEmbedProvider(EmbeddingProvider):
    """CPU-only FastEmbed provider pinned to one exact BGE ONNX model revision."""

    def __init__(self, cache_dir: Path, *, threads: int = 2, local_files_only: bool = False) -> None:
        if threads < 1 or threads > 8:
            raise EmbeddingValidationError("threads must be from 1 through 8")
        self._cache_dir = Path(cache_dir).resolve()
        self._threads = threads
        self._local_files_only = local_files_only
        self._model: Any | None = None
        self._metadata = EmbeddingMetadata(
            "fastembed",
            BGE_MODEL_ID,
            BGE_MODEL_REVISION,
            BGE_DIMENSIONS,
        )

    @property
    def metadata(self) -> EmbeddingMetadata:
        return self._metadata

    def _load(self) -> Any:
        if self._model is None:
            try:
                from fastembed import TextEmbedding
            except ImportError as exc:  # pragma: no cover - environment-specific
                raise RuntimeError("install the companion vector dependencies before loading embeddings") from exc
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            self._model = TextEmbedding(
                model_name=BGE_MODEL_ID,
                cache_dir=str(self._cache_dir),
                threads=self._threads,
                providers=["CPUExecutionProvider"],
                local_files_only=self._local_files_only,
                revision=BGE_MODEL_REVISION,
            )
        return self._model

    def embed_documents(self, texts: Sequence[str], *, batch_size: int = 32) -> list[list[float]]:
        inputs = validate_texts(texts, batch_size=batch_size)
        model = self._load()
        raw = [vector.tolist() for vector in model.embed(inputs, batch_size=batch_size, parallel=None)]
        return validate_vectors(raw, count=len(inputs), dimensions=self.metadata.dimensions)

    def runtime_info(self) -> dict[str, Any]:
        model = self._load()
        return {
            **super().runtime_info(),
            "fastembed": package_metadata.version("fastembed"),
            "onnxruntime": package_metadata.version("onnxruntime"),
            "numpy": package_metadata.version("numpy"),
            "execution_providers": list(model.model.model.get_providers()),
            "cache_dir": str(self._cache_dir),
            "model_source": BGE_MODEL_SOURCE,
        }


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic test double. It is never evidence of semantic embedding execution."""

    def __init__(self, dimensions: int = 8, *, revision: str = "test-only-v1") -> None:
        self._metadata = EmbeddingMetadata("deterministic-mock", "sha256-test-vector", revision, dimensions)

    @property
    def metadata(self) -> EmbeddingMetadata:
        return self._metadata

    def embed_documents(self, texts: Sequence[str], *, batch_size: int = 32) -> list[list[float]]:
        inputs = validate_texts(texts, batch_size=batch_size)
        vectors: list[list[float]] = []
        for text in inputs:
            seed = hashlib.sha256(text.encode("utf-8")).digest()
            values = [((seed[index % len(seed)] / 255.0) * 2.0) - 1.0 for index in range(self.metadata.dimensions)]
            norm = math.sqrt(sum(value * value for value in values)) or 1.0
            vectors.append([value / norm for value in values])
        return validate_vectors(vectors, count=len(inputs), dimensions=self.metadata.dimensions)
