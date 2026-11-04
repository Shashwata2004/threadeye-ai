from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fabricdata.classes import DETECTOR_CLASSES
from fabricdata.operating import Det, Truth
from linescan_domain import generate, guarded_thresholds, verify_sources


def test_domain_sources_require_frozen_train_membership_and_unchanged_pixels(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(b"training image")
    manifest = tmp_path / "frozen_manifest.csv"
    manifest.write_text("original,split\naitex/photo.png,train\n")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    (tmp_path / "sources.json").write_text(json.dumps([{"original": "aitex/photo.png", "path": "source.png", "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]))
    assert len(verify_sources(tmp_path, digest)) == 1
    source.write_bytes(b"different pixels")
    with pytest.raises(ValueError, match="pixels changed"):
        verify_sources(tmp_path, digest)
    manifest.write_text("original,split\naitex/photo.png,test\n")
    with pytest.raises(ValueError, match="non-train"):
        verify_sources(tmp_path, hashlib.sha256(manifest.read_bytes()).hexdigest())


def test_validation_threshold_guards_preserve_defect_floor_and_nuisance_ceiling() -> None:
    box = (0, 0, 10, 10)
    dets = [Det("a", "slub", 0.25, box), Det("b", "loose_thread", 0.2, box)]
    truths = [Truth("a", "slub", box), Truth("b", "loose_thread", box)]
    result = guarded_thresholds(dets, truths, ["slub", "loose_thread", "hand"], {"slub": 0.35, "loose_thread": 0.2, "hand": 0.3})
    assert result["slub"] >= 0.35
    assert result["loose_thread"] <= 0.2
    assert result["hand"] == 0.3


def test_native_strip_generation_clips_boxes_and_preserves_original_annotations(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir()
    records = []
    rows = ["original,split"]
    for code in ("000", "002", "036", "023", "019"):
        name = f"001_{code}_01.png"
        pixels = np.full((248, 640), 100, dtype=np.uint8)
        mask = np.zeros_like(pixels)
        if code != "000":
            mask[20:220, 200:205] = 255
            pixels[mask > 0] = 200
        Image.fromarray(pixels).save(raw / name)
        record = {"original": f"aitex/{name}", "path": name, "kind": "clean" if code == "000" else "defect",
                  "sha256": hashlib.sha256((raw / name).read_bytes()).hexdigest(), "masks": []}
        if code != "000":
            mask_name = f"001_{code}_01_mask.png"
            Image.fromarray(mask).save(raw / mask_name)
            record["masks"].append({"path": mask_name, "sha256": hashlib.sha256((raw / mask_name).read_bytes()).hexdigest()})
        records.append(record)
        rows.append(record["original"] + ",train")
    manifest = raw / "frozen_manifest.csv"
    manifest.write_text("\n".join(rows) + "\n")
    (raw / "sources.json").write_text(json.dumps(records))
    train = {"images": [{"id": 1}], "annotations": [], "categories": [{"id": i + 1, "name": c} for i, c in enumerate(DETECTOR_CLASSES)]}
    result, report = generate(train, raw, out, n=5, seed=12, expected_manifest=hashlib.sha256(manifest.read_bytes()).hexdigest())
    assert len(train["images"]) == 1 and not train["annotations"]
    assert len(result["images"]) == 6 and report["added_images"] == 5
    assert len(report["images"]) == 5 and report["validation_test_unchanged"]
    for annotation in result["annotations"]:
        x, y, w, h = annotation["bbox"]
        assert 0 <= x < x + w <= 640 and 0 <= y < y + h <= 248
    for im in result["images"][1:]:
        assert Image.open(out / im["file_name"]).size == (640, 248)
