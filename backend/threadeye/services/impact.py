"""Paired pilot measurements. No estimated factory savings or invented human baseline."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    roll_id: str = Field(min_length=1)
    method: Literal["manual", "assisted"]
    seconds: float = Field(gt=0)
    truth_defects: int = Field(ge=0)
    missed_defects: int = Field(ge=0)
    false_alarms: int = Field(ge=0)
    usable_yd: float | None = Field(default=None, ge=0)
    loss_bdt: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def check_misses(self) -> Observation:
        if self.missed_defects > self.truth_defects:
            raise ValueError("missed defects cannot exceed independently verified truth defects")
        return self


def read_pilot(path: Path) -> list[Observation]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return [Observation.model_validate({k: v for k, v in row.items() if v != ""}) for row in csv.DictReader(stream)]


def summarize_pilot(observations: list[Observation]) -> dict[str, object]:
    if not observations:
        raise ValueError("pilot has no observations; collect measurements before claiming impact")
    pairs: dict[str, dict[str, Observation]] = defaultdict(dict)
    for row in observations:
        if row.method in pairs[row.roll_id]:
            raise ValueError(f"duplicate {row.method} observation for {row.roll_id}")
        pairs[row.roll_id][row.method] = row
    for roll, pair in pairs.items():
        if set(pair) != {"manual", "assisted"}:
            raise ValueError(f"{roll} needs both manual and assisted observations")
        if pair["manual"].truth_defects != pair["assisted"].truth_defects:
            raise ValueError(f"{roll} has inconsistent independent ground truth")

    def total(method: str, field: str) -> float:
        return sum(float(getattr(pair[method], field)) for pair in pairs.values())

    manual_seconds, assisted_seconds = total("manual", "seconds"), total("assisted", "seconds")
    manual_missed, assisted_missed = total("manual", "missed_defects"), total("assisted", "missed_defects")
    result: dict[str, object] = {
        "paired_rolls": len(pairs),
        "truth_defects": total("manual", "truth_defects"),
        "manual_seconds": manual_seconds,
        "assisted_seconds": assisted_seconds,
        "time_reduction_pct": 100 * (manual_seconds - assisted_seconds) / manual_seconds,
        "manual_missed": manual_missed,
        "assisted_missed": assisted_missed,
        "missed_reduction_pct": 100 * (manual_missed - assisted_missed) / manual_missed if manual_missed else None,
        "manual_false_alarms": total("manual", "false_alarms"),
        "assisted_false_alarms": total("assisted", "false_alarms"),
    }
    for field, label, direction in (("usable_yd", "usable_gain_yd", 1), ("loss_bdt", "loss_reduction_bdt", -1)):
        complete = all(getattr(row, field) is not None for row in observations)
        result[label] = direction * (total("assisted", field) - total("manual", field)) if complete else None
    return result
