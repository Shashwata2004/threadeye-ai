import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))
from linescan_targeted import crop_boxes, split_groups


def test_every_training_batch_and_five_batch_cycle_are_balanced():
    import itertools
    from collections import Counter

    from linescan_targeted import BalancedStream

    kinds = ["target"] * 50 + ["replay"] * 30 + ["clean"] * 20
    stream = iter(BalancedStream(kinds, 42))
    for _ in range(3):
        cycle = []
        for _ in range(5):
            batch = list(itertools.islice(stream, 8))
            cycle.extend(kinds[i] for i in batch)
            assert sum(kinds[i] == "target" for i in batch) == 4
        assert Counter(cycle) == {"target": 20, "replay": 12, "clean": 8}


def test_sliding_camera_clips_a_thin_running_yarn_without_losing_it():
    annotations = [{"category_id": 4, "bbox": [269, 20, 3, 500], "area": 1500}]
    result = crop_boxes(annotations, 200)
    assert result[0]["bbox"] == [269, 0, 3, 248]
    assert crop_boxes(annotations, 600) == []


def test_source_subtype_with_a_single_original_is_not_reserved():
    rows = [
        {
            "source": "aitex",
            "split": "train",
            "original": f"{i:04d}_{subtype}_01.png",
            "group": f"{subtype}-{i}",
            "tile": str(i),
        }
        for subtype, n in [("006", 1), ("002", 8), ("023", 2)]
        for i in range(n)
    ]
    held = split_groups(rows, 42)
    assert "006-0" not in held
    assert len([g for g in held if g.startswith("002-")]) == 2
    assert len([g for g in held if g.startswith("023-")]) == 1
    assert held == split_groups(rows, 42)


def test_preparation_has_exact_balanced_buckets_and_no_group_leakage(tmp_path):
    import csv
    import json
    import tarfile

    import cv2
    from linescan_targeted import prepare

    packed = tmp_path / "packed"
    (packed / "train").mkdir(parents=True)
    categories = [
        {"id": i + 1, "name": name}
        for i, name in enumerate(
            [
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
        )
    ]
    images = []
    anns = []
    rows = []
    raw = tmp_path / "raw"
    raw.mkdir()
    for cls in [0, 3, 4, 5, 7]:
        for n in range(10):
            name = f"{cls}_{n}.jpg"
            image = np.full((640, 640, 3), 140, np.uint8)
            if cls:
                image[10:590, 301:305] = 30
            cv2.imwrite(str(raw / name), image)
            iid = len(images) + 1
            images.append({"id": iid, "file_name": name, "width": 640, "height": 640})
            if cls:
                anns.append(
                    {
                        "id": len(anns) + 1,
                        "image_id": iid,
                        "category_id": cls,
                        "bbox": [301, 10, 4, 580],
                        "area": 2320,
                        "iscrowd": 0,
                    }
                )
            rows.append(
                {
                    "tile": name,
                    "original": name,
                    "source": "wfdd",
                    "split": "train",
                    "group": f"group-{name}",
                }
            )
    (packed / "train/annotations.json").write_text(
        json.dumps({"images": images, "annotations": anns, "categories": categories})
    )
    with (packed / "manifest.csv").open("w") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with tarfile.open(packed / "train.tar", "w") as archive:
        for file in raw.iterdir():
            archive.add(file, arcname=file.name)
    out = tmp_path / "prepared"
    _, report = prepare(packed, out, train_count=100, val_count=100)
    assert report["splits"]["train"]["buckets"] == {
        "target": 50,
        "replay": 30,
        "clean": 20,
    }
    train = json.loads((out / "train/provenance.json").read_text())
    val = json.loads((out / "val/provenance.json").read_text())
    assert not ({r["group"] for r in train} & {r["group"] for r in val})
    for split in ["train", "val"]:
        data = json.loads((out / split / "annotations.json").read_text())
        dims = {i["id"]: (i["width"], i["height"]) for i in data["images"]}
        for annotation in data["annotations"]:
            x, y, w, h = annotation["bbox"]
            width, height = dims[annotation["image_id"]]
            assert 0 <= x < x + w <= width and 0 <= y < y + h <= height
