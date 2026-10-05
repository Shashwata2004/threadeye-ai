# Simulator data contracts

Source of truth: brief §8, plus the conventions the team verified in `tools/simulator/make_roll_video.py`
(PLAN.md §2). Validator: `threadeye validate-dataset <dir>` (`backend/threadeye/datasets/contracts.py`).

| File | Content |
|---|---|
| `roll_meta.json` | `px_per_cm`, `view_region {x,y,w,h}` (= 0,0,1920,1008), `fabric_width_cm`, `fabric_width_in`, `roll_length_yd`, `fps`, `frames`, `expected_score {total_points, points_per_100_sq_yd, threshold, verdict}`, `selvage_band_px`, `mode` (realistic/clean) |
| `frames.csv` | `frame, time_s, roll_y_top_px, top_yd, bottom_yd, speed_m_min, state, fabric_x0_px, hand_visible` |
| `ground_truth.csv` | `defect_id, class, center_yd, start_yd, end_yd, across_cm, length_in, points, first_full_frame, last_full_frame, operator_stop_frame, x0_px, y0_px, x1_px, y1_px, source` |
| `nuisance.csv` | `type (wrinkle/loose_thread/sticker), center_yd, across_cm, extent_cm, appears_frame` (empty = on the fabric from the start; stickers have the frame they are placed in) |
| `roll_video.mp4` | 1920 × 1044; fabric enters at the bottom; 36-px "SIMULATED FEED" bar below `view_region` |

## Conventions (verified)
- `roll_y_px = roll_y_top_px[f] + y`, with `y` measured from the top of `view_region`.
  `yard = roll_y_px / px_per_cm / 91.44`. `across_cm = (x − fabric_x0_px[f]) / px_per_cm`.
- GT boxes are **roll coordinates**: x from the fabric's left edge, y absolute roll px.
  In frame f: `(x + fabric_x0_px[f], y − roll_y_top_px[f])`.
- GT boxes are clipped to exclude the selvage band. Defects fully inside it are not in the answer key.
- `length_in = max(width_cm, height_cm) / 2.54` of the clipped box.
- `expected_score` uses the **simulator-parity** rules: length + hole bands, cell = floor(center_yd),
  cap 4, no continuous, no selvage, no borderline, per-100 from `roll_meta` length × width.
  Sample roll: **10 points, 46.45, FAIL**.

## What the validator checks
Required files and columns; types and ranges per row; contiguous frames; `top_yd` agrees with
`roll_y_top_px`; time is monotonic; unique `defect_id`; GT y-range agrees with start/end yd; `length_in`
agrees with the clipped box; frame indices in range; `expected_score` recomputes and its verdict agrees
with its threshold; class names are known to `taxonomy.yaml` (warning otherwise).

## Test fixture
`backend/tests/fixtures/micro_roll/` is a **synthetic** CSV-only roll from `scripts/make_micro_fixture.py`
(3 defects, 2 nuisances, 205 frames, expected 7 pts / 142.24 / FAIL, hand-checked in the script).
It is not a simulation of fabric and is never used as a demo.
