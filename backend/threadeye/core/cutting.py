"""Conservative whole-width skip zones, with margins and minimum usable pieces."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from threadeye.core.scoring.profile import CuttingPolicy


@dataclass(frozen=True)
class CutDefect:
    start_yd: float
    end_yd: float
    points: int


def cutting_sheet(length_yd: float, defects: Iterable[CutDefect], policy: CuttingPolicy) -> dict[str, object]:
    if not math.isfinite(length_yd) or length_yd <= 0:
        raise ValueError("roll length must be positive and finite")
    margin = policy.margin_in / 36
    zones = []
    for defect in defects:
        if not all(math.isfinite(x) for x in (defect.start_yd, defect.end_yd)):
            raise ValueError("defect positions must be finite")
        if defect.end_yd < defect.start_yd:
            raise ValueError("defect end precedes start")
        if defect.points < policy.min_points_to_cut:
            continue
        start, end = max(0.0, defect.start_yd - margin), min(length_yd, defect.end_yd + margin)
        if end > start:
            zones.append((start, end))
    merged: list[list[float]] = []
    for start, end in sorted(zones):
        if merged and start - merged[-1][1] < policy.min_piece_yd + 1e-9:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    if merged:
        if merged[0][0] < policy.min_piece_yd:
            merged[0][0] = 0.0
        if length_yd - merged[-1][1] < policy.min_piece_yd:
            merged[-1][1] = length_yd
    segments: list[dict[str, Any]] = []
    cursor = 0.0
    for start, end in merged:
        if start > cursor:
            segments.append({"start_yd": cursor, "end_yd": start, "action": "keep"})
        segments.append({"start_yd": start, "end_yd": end, "action": "skip"})
        cursor = end
    if cursor < length_yd:
        # A roll shorter than the minimum piece is not called usable.
        segments.append(
            {
                "start_yd": cursor,
                "end_yd": length_yd,
                "action": "keep" if length_yd - cursor >= policy.min_piece_yd else "skip",
            }
        )
    usable = sum(float(s["end_yd"]) - float(s["start_yd"]) for s in segments if s["action"] == "keep")
    return {
        "length_yd": length_yd,
        "usable_yd": round(usable, 4),
        "skipped_yd": round(length_yd - usable, 4),
        "segments": segments,
        "policy": policy.model_dump(mode="json"),
        "basis": "confirmed defects; conservative whole-width skips",
    }
