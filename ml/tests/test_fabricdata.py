"""Unit tests for the dataset builder (no real data needed)."""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fabricdata import sources  # noqa: E402
from fabricdata.classes import DEFECT_CLASSES, SOURCE_CLASS_MAP, UnmappedClass, map_class  # noqa: E402
from fabricdata.dedupe import fingerprint, merge_near_duplicates  # noqa: E402
from fabricdata.records import Box, ImageRecord  # noqa: E402
from fabricdata.split import assign_splits  # noqa: E402
from fabricdata.tiles import Window, clip, positions, windows  # noqa: E402

TAXONOMY = Path(__file__).resolve().parents[2] / "backend/threadeye/data/taxonomy.yaml"


def test_every_mapped_class_is_a_threadeye_defect() -> None:
    import yaml

    ids = {d["id"] for d in yaml.safe_load(TAXONOMY.read_text())["defects"]}
    assert set(DEFECT_CLASSES) <= ids
    for table in SOURCE_CLASS_MAP.values():
        assert {c for c in table.values() if c is not None} <= set(DEFECT_CLASSES)
    with pytest.raises(UnmappedClass):
        map_class("tianchi", "99")
    assert map_class("garment_defects", "Broken_button") is None


def test_mask_boxes_join_fragments_and_drop_specks() -> None:
    m = np.zeros((100, 200), np.uint8)
    m[10:12, 20:60] = 255  # a thin line broken in two
    m[10:12, 62:90] = 255
    m[50, 150] = 255  # one-pixel speck
    m[70:80, 100:110] = 255
    boxes = sources.mask_boxes(m)
    assert sorted(boxes) == [(20, 10, 90, 12), (100, 70, 110, 80)]


def test_roboflow_names_and_sessions() -> None:
    assert sources.original_name("20240424_133212_jpg.rf.0abc12.jpg") == "20240424_133212"
    items = [("a", datetime(2024, 4, 24, 13, 32, 12)), ("b", datetime(2024, 4, 24, 13, 33, 0)),
             ("c", datetime(2024, 4, 24, 15, 0, 0)), ("d", None)]
    g = sources.session_groups(items, "x")
    assert g["a"] == g["b"] != g["c"] and g["d"] == "x:d"
    assert sources.moratuwa_base("24_processed (3)") == "24" and sources.moratuwa_base("12 (1)") == "12"


def test_tile_positions_cover_the_image() -> None:
    assert positions(500, 640, 0.2) == [(0, 500)]
    ps = positions(2446, 640, 0.2)
    assert ps[0][0] == 0 and ps[-1][1] == 2446 and all(b - a == 640 for a, b in ps)
    assert all(ps[i][1] > ps[i + 1][0] for i in range(len(ps) - 1))  # overlapping
    assert len(windows(2446, 1000)) == len(ps) * len(positions(1000, 640, 0.2))


def test_clip_keeps_visible_and_running_defects() -> None:
    win = Window(0, 0, 640, 640)
    small_half_out = Box(630, 100, 650, 110, "x", "hole")  # 50 % inside
    small_mostly_out = Box(635, 100, 660, 110, "x", "hole")  # 20 % inside
    running = Box(300, 0, 310, 2000, "x", "broken_yarn")  # a long warp fault
    kept = clip([small_half_out, small_mostly_out, running], win)
    assert [(b.x0, b.y1) for b in kept] == [(630, 110), (300, 640)]


def _rec(src: str, name: str, group: str, force: str | None = None) -> ImageRecord:
    return ImageRecord(src, Path(name), 10, 10, [], group=group, force_split=force)


def test_split_keeps_groups_together_honours_forced_and_is_deterministic() -> None:
    recs = [_rec("s", f"{i}.png", f"g{i // 3}") for i in range(300)]
    recs += [_rec("s", "demo1.png", "demo", "test"), _rec("s", "demo2.png", "demo")]
    a, b = assign_splits(recs, seed=1), assign_splits(recs, seed=1)
    assert a == b
    by_group: dict[str, set[str]] = {}
    for r in recs:
        by_group.setdefault(r.group, set()).add(a[r.key])
    assert all(len(s) == 1 for s in by_group.values())
    assert a["s:demo1.png"] == a["s:demo2.png"] == "test"
    counts = {s: list(a.values()).count(s) for s in ("train", "val", "test")}
    assert 220 <= counts["train"] <= 260 and counts["val"] >= 20 and counts["test"] >= 20


def test_copies_across_sources_share_a_group_but_lookalikes_within_a_source_do_not(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    base = (rng.random((64, 128)) * 255).astype(np.uint8)
    shifted = np.clip(base.astype(int) + 3, 0, 255).astype(np.uint8)
    files = {
        "a": ("aitex", base),
        "b": ("moratuwa", shifted),  # a re-upload of a in a compilation
        "c": ("aitex", shifted),  # same look, same source
        "d": ("moratuwa", (rng.random((64, 128)) * 255).astype(np.uint8)),
        "e": ("moratuwa", np.asarray(Image.fromarray(base).resize((128, 128)))),  # different shape
        "z": ("zju_leaper", shifted),  # not a copy-prone source: never compared
    }
    recs = []
    for name, (src, img) in files.items():
        p = tmp_path / f"{name}.png"
        Image.fromarray(img).save(p)
        recs.append(ImageRecord(src, p, img.shape[1], img.shape[0], [], group=name))
    merge_near_duplicates(recs, [fingerprint(r.path) for r in recs])
    g = {r.path.stem: r.group for r in recs}
    assert g["a"] == g["b"] and g["c"] == g["a"]  # c joins through b (cross-source), not through a
    assert g["d"] != g["a"] and g["e"] != g["a"] and g["z"] == "z"


def test_fabric_stain_reader_keeps_both_folders_apart(tmp_path: Path) -> None:
    flat = tmp_path / "flat"
    flat.mkdir()
    for name in ("stain_1", "stain_2", "stain_3", "defect_free_1"):
        Image.new("RGB", (200, 100)).save(flat / f"{name}.jpg")
    (flat / "stain_1.txt").write_text("0 0.5 0.5 0.2 0.4\n0 0.1 0.1 0.1 0.1\n")
    (flat / "stain_2.txt").write_text("0 0.5 0.5 0.1 0.1\n")
    (flat / "defect_free_1.txt").write_text("")
    recs = {r.path.stem: r for r in sources.read_fabric_stain(tmp_path)}
    assert len({r.key for r in recs.values()}) == 3
    b = recs["stain_1"].boxes[0]
    assert (b.x0, b.y0, b.x1, b.y1) == pytest.approx((80, 30, 120, 70))
    assert map_class("fabric_stain", b.src_cls) == "stain"
    assert "stain_3" not in recs  # a stain photo without labels is left out
    assert recs["defect_free_1"].defect_free and recs["defect_free_1"].group != recs["stain_1"].group
    assert recs["stain_1"].group == recs["stain_2"].group  # consecutive shots stay together
