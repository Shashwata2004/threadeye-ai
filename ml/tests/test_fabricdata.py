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
from fabricdata.classes import (  # noqa: E402
    DEFECT_CLASSES,
    DETECTOR_CLASSES,
    NUISANCE_CLASSES,
    SOURCE_CLASS_MAP,
    UnmappedClass,
    map_class,
)
from fabricdata.dedupe import fingerprint, merge_near_duplicates  # noqa: E402
from fabricdata.records import Box, ImageRecord  # noqa: E402
from fabricdata.split import assign_splits  # noqa: E402
from fabricdata.tiles import Window, clip, positions, windows  # noqa: E402

TAXONOMY = Path(__file__).resolve().parents[2] / "backend/threadeye/data/taxonomy.yaml"


def test_every_mapped_class_is_a_threadeye_class() -> None:
    import yaml

    tax = yaml.safe_load(TAXONOMY.read_text())
    assert set(DEFECT_CLASSES) <= {d["id"] for d in tax["defects"]}
    assert set(NUISANCE_CLASSES) <= {d["id"] for d in tax["nondefects"]}
    for table in SOURCE_CLASS_MAP.values():
        assert {c for c in table.values() if c is not None} <= set(DETECTOR_CLASSES)
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


def test_nuisances_are_drawn_with_boxes_and_never_cover_a_defect() -> None:
    from fabricdata import nuisance

    rng = np.random.default_rng(3)
    defect = (300.0, 300.0, 340.0, 340.0)
    seen = set()
    for _ in range(40):
        img = np.full((640, 640, 3), 140.0, np.float32) + rng.normal(0, 8, (640, 640, 3)).astype(np.float32)
        before = img[300:340, 300:340].copy()
        drawn = nuisance.compose(img, rng, hands=[], keep_clear=[defect])
        for d in drawn:
            assert d.cls in NUISANCE_CLASSES
            x0, y0, x1, y1 = d.box
            assert 0 <= x0 < x1 <= 640 and 0 <= y0 < y1 <= 640
            assert not nuisance.overlaps(nuisance._grow(d.box, nuisance.CLEAR_MARGIN), [defect])
            seen.add(d.cls)
        if not any(d.cls == "wrinkle" for d in drawn):  # a wrinkle may shade nearby cloth, nothing else may
            assert np.array_equal(img[300:340, 300:340], before)
    assert seen == set(NUISANCE_CLASSES)


def test_operating_point_counts_what_an_inspector_sees() -> None:
    from fabricdata.operating import Det, Truth, choose_thresholds, report

    truths = [Truth("a", "hole", (10, 10, 30, 30)), Truth("a", "broken_yarn", (100, 0, 104, 600)),
              Truth("b", "stain", (50, 50, 90, 90)), Truth("b", "sticker", (300, 300, 340, 330))]
    dets = [
        Det("a", "hole", 0.9, (11, 11, 31, 29)),
        Det("a", "hole", 0.8, (12, 10, 30, 30)),  # duplicate of the same hole: not a false alarm
        Det("a", "broken_yarn", 0.6, (98, 200, 106, 260)),  # low IoU, centre inside: found
        Det("b", "hole", 0.7, (52, 52, 88, 88)),  # the stain, called a hole: found, wrong class
        Det("b", "stain", 0.5, (301, 301, 339, 329)),  # the sticker, called a stain
        Det("c", "knot", 0.4, (5, 5, 15, 15)),  # nothing there
        Det("c", "knot", 0.1, (50, 5, 60, 15)),  # below the knot threshold
    ]
    thr = {"hole": 0.3, "stain": 0.3, "broken_yarn": 0.3, "knot": 0.3, "sticker": 0.3}
    r = report(dets, truths, thr, {"hole", "stain", "broken_yarn", "knot"}, lambda im: "src", ["a", "b", "c"])
    assert r["defects"] == 3 and r["found_any_class"] == 1.0 and r["found_right_class"] == round(2 / 3, 4)
    assert r["false_alarms"] == 2  # the sticker-as-stain and the empty knot
    assert r["precision"] == 0.6  # 3 boxes on real defects (the duplicate not counted), 2 false alarms
    assert r["nondefects_called_defect"] == 1.0
    assert r["per_class"]["hole"]["precision"] == 0.5  # the hole (its duplicate not counted) and the stain
    assert r["per_source"]["src"]["tiles"] == 3
    chosen = choose_thresholds(dets, truths, ["hole", "knot"])
    assert chosen["hole"] >= 0.05 and chosen["knot"] == 0.3  # no knot in the truth: default
