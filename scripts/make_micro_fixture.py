#!/usr/bin/env python3
"""Write the synthetic micro-fixture roll (CSV/JSON only, no images) used by tests until, and
alongside, the real simulator sample roll. Same file formats and conventions as the simulator
(brief §8, PLAN.md §2 "Simulator conventions"). Deterministic: running it again gives identical files.

    python3 scripts/make_micro_fixture.py backend/tests/fixtures/micro_roll

SYNTHETIC TEST DATA. It is not a simulation of real fabric and is never shown as a demo.

Hand-checked expected score (simulator-parity rules):
  D1 hole   0.8 cm → 0.315 in → hole ≤ 1 in → 2 pts, cell floor(0.50) = 0
  D2 stain 12 x 6 cm → 4.724 in → 3–6 in   → 2 pts, cell floor(1.60) = 1
  D3 slub  20 x 1 cm → 7.874 in → 6–9 in   → 3 pts, cell floor(2.40) = 2
  total 7 pts; per-100 = 7 * 3600 / (3.0 yd * 59.055 in) = 142.24 → FAIL (threshold 40)
"""

from __future__ import annotations

import csv
import json
import math
import sys
from pathlib import Path

PX_PER_CM = 10.0
VIEW = {"x": 0, "y": 0, "w": 1920, "h": 1008}
FABRIC_WIDTH_CM = 150.0
FABRIC_WIDTH_IN = round(FABRIC_WIDTH_CM / 2.54, 3)  # 59.055
ROLL_LENGTH_YD = 3.0
FPS = 30.0
YARD_PX = 91.44 * PX_PER_CM  # 914.4 px per yard
SPEED_PX_PER_FRAME = 10.0  # 300 px/s = 30 cm/s = 18 m/min
STOP_AT_FRAME, STOP_FRAMES = 100, 30  # operator stops at D2 (fabric still, hand visible)
SELVAGE_BAND_PX = 15.0

# defect_id, class, center_yd, across_cm (box centre from the fabric's left edge), w_cm, h_cm
DEFECTS = [
    ("D1", "hole", 0.50, 40.0, 0.8, 0.8, 2),
    ("D2", "stain", 1.60, 75.0, 12.0, 6.0, 2),
    ("D3", "slub", 2.40, 110.0, 1.0, 20.0, 3),
]
NUISANCE = [
    # type, center_yd, across_cm, extent_cm, appears_frame
    ("sticker", 1.62, 2.5, 5.0, STOP_AT_FRAME + 10),
    ("loose_thread", 2.00, 90.0, 8.0, 0),
]


def frames() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    end_top_px = ROLL_LENGTH_YD * YARD_PX - VIEW["h"]  # last frame shows the roll's end at the bottom
    y = 0.0
    f = 0
    while True:
        stopped = STOP_AT_FRAME <= f < STOP_AT_FRAME + STOP_FRAMES
        speed = 0.0 if stopped else SPEED_PX_PER_FRAME * FPS / PX_PER_CM * 60 / 100  # m/min
        rows.append(
            {
                "frame": f,
                "time_s": round(f / FPS, 4),
                "roll_y_top_px": round(y, 3),
                "top_yd": round(y / YARD_PX, 5),
                "bottom_yd": round((y + VIEW["h"]) / YARD_PX, 5),
                "speed_m_min": round(speed, 3),
                "state": "stopped" if stopped else "running",
                "fabric_x0_px": round(210.0 + 12.0 * math.sin(f / 40.0), 3),
                "hand_visible": 1 if STOP_AT_FRAME + 5 <= f < STOP_AT_FRAME + 25 else 0,
            }
        )
        if y >= end_top_px:
            break
        if not stopped:
            y = min(y + SPEED_PX_PER_FRAME, end_top_px)
        f += 1
    return rows


def first_last_full(y0: float, y1: float, fr: list[dict[str, object]]) -> tuple[int, int]:
    inside = [
        int(r["frame"])  # type: ignore[call-overload]
        for r in fr
        if float(r["roll_y_top_px"]) <= y0 and y1 <= float(r["roll_y_top_px"]) + VIEW["h"]  # type: ignore[arg-type]
    ]
    return inside[0], inside[-1]


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fr = frames()
    total = sum(d[6] for d in DEFECTS)
    per_100 = round(total * 3600 / (ROLL_LENGTH_YD * FABRIC_WIDTH_IN), 2)
    meta = {
        "px_per_cm": PX_PER_CM,
        "view_region": VIEW,
        "fabric_width_cm": FABRIC_WIDTH_CM,
        "fabric_width_in": FABRIC_WIDTH_IN,
        "roll_length_yd": ROLL_LENGTH_YD,
        "fps": FPS,
        "frames": len(fr),
        "expected_score": {
            "total_points": total,
            "points_per_100_sq_yd": per_100,
            "threshold": 40,
            "verdict": "PASS" if per_100 <= 40 else "FAIL",
        },
        "selvage_band_px": SELVAGE_BAND_PX,
        "mode": "clean",
        "fixture_note": "SYNTHETIC micro-fixture for tests (scripts/make_micro_fixture.py); not a simulation.",
    }
    (out / "roll_meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")

    with (out / "frames.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(fr[0].keys()))
        w.writeheader()
        w.writerows(fr)

    gt_rows = []
    for did, cls, cyd, across, w_cm, h_cm, pts in DEFECTS:
        cy_px = cyd * YARD_PX
        x0, x1 = (across - w_cm / 2) * PX_PER_CM, (across + w_cm / 2) * PX_PER_CM
        y0, y1 = cy_px - h_cm / 2 * PX_PER_CM, cy_px + h_cm / 2 * PX_PER_CM
        first, last = first_last_full(y0, y1, fr)
        gt_rows.append(
            {
                "defect_id": did,
                "class": cls,
                "center_yd": round(cyd, 5),
                "start_yd": round(y0 / YARD_PX, 5),
                "end_yd": round(y1 / YARD_PX, 5),
                "across_cm": across,
                "length_in": round(max(w_cm, h_cm) / 2.54, 4),
                "points": pts,
                "first_full_frame": first,
                "last_full_frame": last,
                "operator_stop_frame": STOP_AT_FRAME if did == "D2" else "",
                "x0_px": round(x0, 2),
                "y0_px": round(y0, 2),
                "x1_px": round(x1, 2),
                "y1_px": round(y1, 2),
                "source": "synthetic_fixture",
            }
        )
    with (out / "ground_truth.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(gt_rows[0].keys()))
        w.writeheader()
        w.writerows(gt_rows)

    with (out / "nuisance.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["type", "center_yd", "across_cm", "extent_cm", "appears_frame"])
        w.writerows(NUISANCE)

    print(f"wrote micro-fixture to {out}: {len(fr)} frames, {len(DEFECTS)} defects, "
          f"expected {total} pts / {per_100} → {meta['expected_score']['verdict']}")  # type: ignore[index]


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "backend/tests/fixtures/micro_roll"))
