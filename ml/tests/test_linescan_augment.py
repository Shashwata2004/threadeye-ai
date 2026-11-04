from __future__ import annotations

import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from linescan_augment import augment


def fixture(tmp_path: Path) -> tuple[dict, Path]:
    images = tmp_path / "images"
    images.mkdir()
    Image.new("RGB", (640, 640), (90, 120, 90)).save(images / "aitex__train.jpg")
    return {"images": [{"id": 1, "file_name": "aitex__train.jpg", "width": 640, "height": 640}],
            "annotations": [{"id": 1, "image_id": 1, "category_id": 1, "bbox": [100, 100, 200, 3]},
                            {"id": 2, "image_id": 1, "category_id": 2, "bbox": [110, 80, 20, 20]}],
            "categories": [{"id": 1, "name": "broken_yarn"}, {"id": 2, "name": "sticker"}]}, images


def test_augmentation_retains_all_labels_and_does_not_mutate_original(tmp_path: Path) -> None:
    train, images = fixture(tmp_path)
    merged, report = augment(train, images, tmp_path / "out", n=3)
    assert len(train["images"]) == 1 and len(train["annotations"]) == 2
    assert len(merged["images"]) == 4
    assert {a["category_id"] for a in merged["annotations"] if a["image_id"] > 1} == {1, 2}
    assert len({a["id"] for a in merged["annotations"]}) == len(merged["annotations"])
    for annotation in merged["annotations"]:
        x, y, w, h = annotation["bbox"]
        assert 0 <= x < x + w <= 640 and 0 <= y < y + h <= 640
    assert report["split"] == "train" and report["validation_test_unchanged"]
    assert all(d["tile"] == "aitex__train.jpg" for im in report["images"] for d in im["donors"])
    second, _ = augment(train, images, tmp_path / "repeat", n=3)
    assert second == merged
    for im in report["images"]:
        assert (tmp_path / "out" / im["file"]).read_bytes() == (tmp_path / "repeat" / im["file"]).read_bytes()


def test_heldout_donors_are_rejected_before_any_output(tmp_path: Path) -> None:
    train, images = fixture(tmp_path)
    with pytest.raises(ValueError, match="overlap"):
        augment(train, images, tmp_path / "out", n=1, forbidden={"aitex__train.jpg"})
    assert not (tmp_path / "out").exists()
