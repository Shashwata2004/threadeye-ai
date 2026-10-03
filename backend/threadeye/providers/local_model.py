"""LocalModelDetector: STUB until the training track delivers an ONNX model (M6, owner C).

TODO (PLAN.md §10 training track, §13):
- ONNX Runtime (CPU first) loading model_versions.artifact_key; verify SHA-256 before use.
- Model card: classes, input size, preprocessing, per-class thresholds, training dataset ids,
  split hashes, test metrics.
- Tile 1920-px frames with overlap + NMS; warm up in prepare(); optional batching.
- Lives in the edge worker image ([vision, onnx] extras); not part of the cloud bundle.
- Benchmark only on split=test; evaluation refuses datasets overlapping trained_on_dataset_ids.
- Must pass tests/conformance before activation.
"""

from __future__ import annotations

from threadeye.core.frames import FramePacket
from threadeye.core.providers import (
    DetectionResult,
    DetectorProvider,
    ProviderInfo,
    ProviderNotConfigured,
)


class LocalModelDetector(DetectorProvider):
    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo(
            provider_id="local_model",
            version="0.0.0",
            display_name="ThreadEye local model (no model installed)",
            kind="local_model",
            is_simulated=False,
            requires_image=True,
            calibrated_confidence=False,
            bbox_quality="precise",
            classes=(),
            config_hash="stub",
        )

    def detect(self, frame: FramePacket) -> DetectionResult:
        raise ProviderNotConfigured("LocalModelDetector: no model installed yet (training track, M6)")
