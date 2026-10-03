"""ApiDetector: STUB. No external AI API is called in this phase (brief §7, §13).

TODO (only if the team decides to add it; PLAN.md §13):
- HTTP client with timeouts, retries/backoff and a circuit breaker; API key from env only.
- Versioned prompt + JSON schema in providers/prompts/ (also recorded in PROMPTS.md).
- Strict response validation; bbox normalisation (normalised/approximate → bbox_quality="approximate").
- Class mapping provider label → taxonomy (unknown → other_defect, flagged).
- Per-call latency/cost logging; cache by frame SHA-256.
- Privacy gate: OFF by default. Admin must record consent because images leave the factory.
- Never fall back to the simulator on failure: return DetectionResult(error=...).
- Must pass tests/conformance before it can be activated.
"""

from __future__ import annotations

from threadeye.core.frames import FramePacket
from threadeye.core.providers import (
    DetectionResult,
    DetectorProvider,
    ProviderInfo,
    ProviderNotConfigured,
)


class ApiDetector(DetectorProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="api",
            version="0.0.0",
            display_name="External AI API detector (not configured)",
            kind="api",
            is_simulated=False,
            requires_image=True,
            calibrated_confidence=False,
            bbox_quality="approximate",
            classes=(),
            config_hash="stub",
        )

    def detect(self, frame: FramePacket) -> DetectionResult:
        raise ProviderNotConfigured("ApiDetector is a stub (PLAN.md §13)")
