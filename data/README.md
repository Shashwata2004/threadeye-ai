# data/

| Folder | Content | Status |
|---|---|---|
| `sample_roll/` | One **SIMULATED** roll from our simulator (`tools/simulator/`, realistic mode, AITEX fabric 02, seed 11): `roll_video.mp4, frames.csv, ground_truth.csv, nuisance.csv, roll_meta.json, roll_preview.png, SHA256SUMS`. Expected score: 10 points, 46.45 per 100 sq yd, FAIL | In the repo except `roll_video.mp4` (see below). Check with `make validate-sample` and `sha256sum -c SHA256SUMS` |
| `generated/` | Extra simulated rolls (gitignored, from M4) | — |

All data here is simulated from the AITEX Fabric Image Database. It is not factory data and is always
labelled SIMULATED. The video is committed only after the licence check (PLAN.md Q2; `.gitignore`
excludes `*.mp4` until then). Formats: `docs/data-contracts.md`.

`roll_video.mp4` is not in git. Get it from the team and put it in `data/sample_roll/`; its SHA-256 is
in `SHA256SUMS` (`sha256sum -c SHA256SUMS` reports it missing until then). Without it everything
except the live screen's video still works: tests, `make run-sample`, and the headless pipeline only
need the CSV/JSON files.
