# data/

| Folder | Content | Status |
|---|---|---|
| `sample_roll/` | One **SIMULATED** roll from our simulator (`tools/simulator/`, realistic mode, AITEX fabric 02, seed 11): `roll_video.mp4, frames.csv, ground_truth.csv, nuisance.csv, roll_meta.json, roll_preview.png, SHA256SUMS`. Expected score: 10 points, 46.45 per 100 sq yd, FAIL | In the repo except `roll_video.mp4` (see below). Check with `make validate-sample` and `sha256sum -c SHA256SUMS` |
| `linescan_roll/` | The **demo roll** (SIMULATED, shown first): the same AITEX fabric 02 seen as a line-scan camera sees it, one untouched AITEX strip per frame (no joins), 4K wide (3840×284), 20 m/min = 3.19 frames/s, 12 m, AITEX's own grey pixels with no added camera noise, blur or vignette (`make_roll_video.py --source aitex --dataset data/external/aitex/extracted --fabric-id 02 --mode realistic --seed 11 --roll-length-m 12 --frame-width 3840 --noise 0 --vignette 0 --exposure-s 0.00001 --linescan`). Expected score: 9 points, 41.81 per 100 sq yd, FAIL | Like `sample_roll/`: everything in the repo except `roll_video.mp4` |
| `generated/` | Extra simulated rolls (gitignored, from M4) | — |

All data here is simulated from the AITEX Fabric Image Database. It is not factory data and is always
labelled SIMULATED. The video is committed only after the licence check (PLAN.md Q2; `.gitignore`
excludes `*.mp4` until then). Formats: `docs/data-contracts.md`.

`roll_video.mp4` is not in git. Get it from the team (or `threadeye fetch-demo-assets`) and put it in its roll
folder; its SHA-256 is in that folder's `SHA256SUMS` (`sha256sum -c SHA256SUMS` reports it missing until then). Without it everything
except the live screen's video still works: tests, `make run-sample`, and the headless pipeline only
need the CSV/JSON files.
