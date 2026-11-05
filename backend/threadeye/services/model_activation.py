"""A validated local model must not be overwritten by the shared demo asset downloader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

MODEL_FILES = ("threadeye_s.onnx", "model_info.json", "test_report.json")
ACTIVATION = "local_activation.json"


def validated_local_model(directory: Path) -> bool:
    marker = directory / ACTIVATION
    if not marker.is_file():
        return False
    data = json.loads(marker.read_text())
    if data.get("release_passed") is not True:
        raise ValueError("local model activation has no passing release report")
    for name in MODEL_FILES:
        path = directory / name
        expected = data.get("sha256", {}).get(name)
        if not path.is_file() or not expected or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"activated local model changed or is missing: {name}; restore its backup")
    return True
