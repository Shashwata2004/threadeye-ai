from pathlib import Path

import pytest

from threadeye.services.datasets import get_dataset, list_datasets

META = '{"roll_length_yd": 13.1, "fabric_width_in": 59.06, "fabric_width_cm": 150, "frames": 2, "fps": 3.2}'


def _roll(base: Path, name: str, hidden: bool = False) -> None:
    d = base / name
    d.mkdir()
    (d / "roll_meta.json").write_text(META)
    (d / "frames.csv").write_text("frame\n0\n")
    if hidden:
        (d / "HIDDEN").write_text("old demo roll\n")


def test_hidden_rolls_are_not_offered_but_open_by_id(tmp_path: Path) -> None:
    _roll(tmp_path, "sample_roll", hidden=True)
    _roll(tmp_path, "linescan_roll")
    _roll(tmp_path, "other_roll")
    assert [d.id for d in list_datasets(tmp_path)] == ["linescan_roll", "other_roll"]
    assert get_dataset("sample_roll", tmp_path).id == "sample_roll"


def test_unknown_roll(tmp_path: Path) -> None:
    from threadeye.services.datasets import DatasetNotFound

    with pytest.raises(DatasetNotFound):
        get_dataset("nope", tmp_path)
