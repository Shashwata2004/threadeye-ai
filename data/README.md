# data/

| Folder | Content | Status |
|---|---|---|
| `sample_roll/` | One **SIMULATED** roll from our simulator: `roll_video.mp4, frames.csv, ground_truth.csv, nuisance.csv, roll_meta.json, roll_preview.png` | Arrives from the team; validate with `make validate-sample` |
| `generated/` | Extra simulated rolls (gitignored, from M4) | — |

All data here is simulated from the AITEX Fabric Image Database. It is not factory data and is always
labelled SIMULATED. The video is committed only after the licence check (PLAN.md Q2; `.gitignore`
excludes `*.mp4` until then). Formats: `docs/data-contracts.md`.
