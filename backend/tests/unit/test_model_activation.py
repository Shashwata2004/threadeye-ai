import hashlib
import json

import pytest

from threadeye.services.model_activation import ACTIVATION, MODEL_FILES, validated_local_model


def test_normal_shared_model_has_no_local_pin(tmp_path):
    assert not validated_local_model(tmp_path)


def test_local_pin_requires_passing_release_and_exact_all_artifacts(tmp_path):
    files = {name: name.encode() for name in MODEL_FILES}
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    marker = {"release_passed": True, "sha256": {n: hashlib.sha256(b).hexdigest() for n, b in files.items()}}
    (tmp_path / ACTIVATION).write_text(json.dumps(marker))
    assert validated_local_model(tmp_path)
    (tmp_path / "model_info.json").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed or is missing"):
        validated_local_model(tmp_path)
    marker["release_passed"] = False
    (tmp_path / ACTIVATION).write_text(json.dumps(marker))
    with pytest.raises(ValueError, match="no passing release"):
        validated_local_model(tmp_path)
