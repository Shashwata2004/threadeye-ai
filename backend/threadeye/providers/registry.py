"""Provider registry: provider_id → implementation + availability shown in the UI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from threadeye.core.providers import DetectorProvider, ProviderContext, ProviderKind
from threadeye.providers.api_detector import ApiDetector
from threadeye.providers.local_model import LocalModelDetector
from threadeye.providers.simulated import SimulatedDetector

Availability = Literal["available", "planned", "stub"]


@dataclass(frozen=True)
class ProviderSpec:
    provider_id: str
    display_name: str
    kind: ProviderKind
    is_simulated: bool
    availability: Availability
    milestone: str
    note: str
    cls: type[DetectorProvider]


REGISTRY: Mapping[str, ProviderSpec] = {
    "simulated": ProviderSpec(
        "simulated",
        "Simulated detector (answer key, not AI)",
        "simulated",
        True,
        "available",
        "M1",
        "Reads the simulator's answer key; imperfections are configurable. Not AI.",
        SimulatedDetector,
    ),
    "local_model": ProviderSpec(
        "local_model",
        "ThreadEye local model (ONNX, CPU)",
        "local_model",
        False,
        "available",
        "M6",
        "Our own trained detector (YOLOX-S, ONNX Runtime on the CPU). Needs the model files in THREADEYE_MODEL_DIR.",
        LocalModelDetector,
    ),
    "api": ProviderSpec(
        "api",
        "External AI API",
        "api",
        False,
        "stub",
        "-",
        "Not planned for this phase; no external AI API is called.",
        ApiDetector,
    ),
}


def create_provider(
    provider_id: str, config: Mapping[str, Any] | None = None, ctx: ProviderContext | None = None
) -> DetectorProvider:
    try:
        spec = REGISTRY[provider_id]
    except KeyError as exc:
        raise ValueError(f"unknown provider {provider_id!r}; known: {', '.join(REGISTRY)}") from exc
    return spec.cls(config or {}, ctx or ProviderContext())
