import sys
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))
import linescan_rendered as rendered


def test_rendered_camera_frames_use_real_renderer_and_isolate_all_backgrounds(
    tmp_path, monkeypatch
):
    raw = tmp_path / "raw"
    raw.mkdir()
    full = tmp_path / "aitex"
    full.mkdir()
    (full / "sources.json").write_text("[]")
    names = [
        "hole",
        "stain",
        "slub",
        "broken_yarn",
        "missing_yarn",
        "knot",
        "crease_mark",
        "contamination",
        "shade_bar",
        "other_defect",
        "sticker",
        "loose_thread",
        "wrinkle",
        "hand",
    ]
    categories = {n + 1: name for n, name in enumerate(names)}
    pools = {}
    for split in ("train", "val"):
        items = []
        for kind in ("target", "clean"):
            name = f"{split}-{kind}.png"
            yy, xx = np.mgrid[:640, :640]
            pixels = (130 + 12 * np.sin(xx * 1.9) + 8 * np.sin(yy * 0.7)).astype(
                np.uint8
            )
            image = np.repeat(pixels[..., None], 3, axis=2)
            if kind == "target":
                image[10:620, 310:314] = 20
            cv2.imwrite(str(raw / name), image)
            items.append(
                {
                    "image": {"file_name": name},
                    "annotations": [{"category_id": 4, "bbox": [310, 10, 4, 610]}]
                    if kind == "target"
                    else [],
                    "manifest": {
                        "source": "wfdd",
                        "original": name,
                        "group": f"wfdd:grey_cloth:{split}-{kind}",
                    },
                }
            )
        pools[split] = {
            "replay": items,
            "clean": [items[1]],
            "target": {"broken_yarn": [items[0]]},
        }
    calls = []
    real = rendered.render_fabric_view

    def observed(renderer, *args, **kwargs):
        assert isinstance(renderer, rendered.RollRenderer)
        assert isinstance(renderer.src, rendered.DatasetSource)
        calls.append(renderer)
        return real(renderer, *args, **kwargs)

    monkeypatch.setattr(rendered, "render_fabric_view", observed)
    bank = rendered.RenderedViews(raw, tmp_path / "render", pools, categories, full, 42)
    used = {}
    alignments = set()
    for split in pools:
        used[split] = set()
        for phase in [0, 10, 20, 30, 40]:
            image, annotations, provenance = bank.render(
                split,
                pools[split]["target"]["broken_yarn"][0],
                "broken_yarn",
                phase,
                "target",
            )
            assert any(a["category_id"] == 4 for a in annotations)
            assert image.shape[1] == 640
            for ann in annotations:
                x, y, w, h = ann["bbox"]
                assert 0 <= x < x + w <= 640
                assert 0 <= y < y + h <= image.shape[0]
            used[split].update(provenance["groups"])
            alignments.add(provenance["camera_alignment"])
        for index in [0, 1, 2]:
            _image, aa, proof = bank.render(
                split, pools[split]["clean"][0], None, index, "clean"
            )
            assert all(a["category_id"] in (11, 12, 13) for a in aa)
            assert proof["reference_originals"] == [f"{split}-clean.png"]
            used[split].update(proof["groups"])
    assert calls
    assert alignments == {"source-strip", "partial-edge"}
    assert not used["train"] & used["val"]
