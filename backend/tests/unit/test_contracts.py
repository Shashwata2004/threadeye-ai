"""Data-contract validators against the synthetic micro-fixture (and the real sample roll if present)."""

import csv
import json
import shutil
from pathlib import Path

import pytest

from tests.conftest import MICRO_ROLL, SAMPLE_ROLL
from threadeye.datasets.contracts import validate_dataset


def copy_fixture(tmp_path: Path) -> Path:
    dst = tmp_path / "roll"
    shutil.copytree(MICRO_ROLL, dst)
    return dst


def rewrite_csv(path: Path, mutate) -> None:  # type: ignore[no-untyped-def]
    with path.open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    fields = list(rows[0].keys())
    rows, fields = mutate(rows, fields)
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def test_micro_fixture_is_valid() -> None:
    report, parsed = validate_dataset(MICRO_ROLL, require_media=False)
    assert report.ok, report.errors
    assert parsed is not None
    assert [w.file for w in report.warnings] == ["roll_video.mp4", "roll_preview.png"]
    assert report.summary["defects"] == 3
    assert report.summary["nuisances"] == 2
    assert report.summary["stopped_frames"] == 30
    assert parsed.meta.expected_score.total_points == 7
    assert parsed.ground_truth[1].operator_stop_frame == 100
    assert parsed.ground_truth[0].operator_stop_frame is None  # blank → None


def test_media_required_by_default() -> None:
    report, parsed = validate_dataset(MICRO_ROLL)
    assert not report.ok and parsed is None
    assert any(e.file == "roll_video.mp4" for e in report.errors)


def _errors_after(tmp_path: Path, file: str, mutate) -> list[str]:  # type: ignore[no-untyped-def]
    root = copy_fixture(tmp_path)
    if file.endswith(".json"):
        meta = json.loads((root / file).read_text())
        mutate(meta)
        (root / file).write_text(json.dumps(meta))
    else:
        rewrite_csv(root / file, mutate)
    report, parsed = validate_dataset(root, require_media=False)
    assert parsed is None
    return [str(e) for e in report.errors]


def test_missing_column(tmp_path: Path) -> None:
    def drop(rows, fields):  # type: ignore[no-untyped-def]
        return [{k: v for k, v in r.items() if k != "hand_visible"} for r in rows], [
            f for f in fields if f != "hand_visible"
        ]

    errs = _errors_after(tmp_path, "frames.csv", drop)
    assert any("missing columns: hand_visible" in e for e in errs)


def test_duplicate_defect_id(tmp_path: Path) -> None:
    def dup(rows, fields):  # type: ignore[no-untyped-def]
        rows[1]["defect_id"] = rows[0]["defect_id"]
        return rows, fields

    assert any("duplicate defect_id" in e for e in _errors_after(tmp_path, "ground_truth.csv", dup))


def test_length_in_must_match_clipped_box(tmp_path: Path) -> None:
    def wrong(rows, fields):  # type: ignore[no-untyped-def]
        rows[2]["length_in"] = "3.0"
        return rows, fields

    assert any("length_in" in e for e in _errors_after(tmp_path, "ground_truth.csv", wrong))


def test_gt_y_must_match_start_end_yd(tmp_path: Path) -> None:
    def shift(rows, fields):  # type: ignore[no-untyped-def]
        rows[0]["start_yd"] = "0.3"
        rows[0]["center_yd"] = "0.4"
        return rows, fields

    assert any("disagree with start/end yd" in e for e in _errors_after(tmp_path, "ground_truth.csv", shift))


def test_frames_must_be_contiguous(tmp_path: Path) -> None:
    def gap(rows, fields):  # type: ignore[no-untyped-def]
        del rows[10]
        return rows, fields

    errs = _errors_after(tmp_path, "frames.csv", gap)
    assert any("contiguous" in e for e in errs)


def test_expected_score_recomputed(tmp_path: Path) -> None:
    def bad(meta):  # type: ignore[no-untyped-def]
        meta["expected_score"]["points_per_100_sq_yd"] = 99.9

    assert any("recomputed" in e for e in _errors_after(tmp_path, "roll_meta.json", bad))


def test_nuisance_type_is_restricted(tmp_path: Path) -> None:
    def bad(rows, fields):  # type: ignore[no-untyped-def]
        rows[0]["type"] = "cat"
        return rows, fields

    assert any("nuisance.csv" in e for e in _errors_after(tmp_path, "nuisance.csv", bad))


@pytest.mark.skipif(not (SAMPLE_ROLL / "roll_meta.json").exists(), reason="sample roll not in repo yet")
def test_real_sample_roll_is_valid() -> None:
    report, parsed = validate_dataset(SAMPLE_ROLL)
    assert report.ok, report.errors
    assert parsed is not None
    es = parsed.meta.expected_score
    assert (es.total_points, round(es.points_per_100_sq_yd, 2), es.verdict) == (10, 46.45, "FAIL")
