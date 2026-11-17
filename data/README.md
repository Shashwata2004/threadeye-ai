# data/

| Folder | Content | Status |
|---|---|---|
| `sample_roll/` | The first demo roll, now kept for the tests only (its `HIDDEN` file keeps it out of the app's roll list): one **SIMULATED** roll from our simulator (`tools/simulator/`, realistic mode, AITEX fabric 02, seed 11): `roll_video.mp4, frames.csv, ground_truth.csv, nuisance.csv, roll_meta.json, roll_preview.png, SHA256SUMS`. Expected score: 10 points, 46.45 per 100 sq yd, FAIL | Bundled in Git, including `roll_video.mp4`. Check with `make validate-sample` and `sha256sum -c SHA256SUMS` |
| `linescan_roll/` | The **demo roll** (SIMULATED, the roll the app offers): the same AITEX fabric 02 seen as a line-scan camera sees it, one untouched AITEX strip per frame (no joins), 4K wide (3840×284), 20 m/min = 3.19 frames/s, 12 m, AITEX's own grey pixels with no added camera noise, blur or vignette (`make_roll_video.py --source aitex --dataset data/external/aitex/extracted --fabric-id 02 --mode realistic --seed 11 --roll-length-m 12 --frame-width 3840 --noise 0 --vignette 0 --exposure-s 0.00001 --linescan`). Expected score: 9 points, 41.81 per 100 sq yd, FAIL | Bundled in Git, including `roll_video.mp4` |
| `generated/` | Extra simulated rolls (gitignored, from M4) | — |

All data here is simulated from the AITEX Fabric Image Database. It is not factory data and is always
labelled SIMULATED. The five named team-demo videos and stable model are bundled in Git; ad-hoc
simulator outputs and candidate models remain ignored. Source licence questions (PLAN.md Q2) remain
recorded in `PROVENANCE.md`; bundling does not establish additional redistribution rights.
Formats: `docs/data-contracts.md`.

Run `make assets-check` after cloning: it verifies the five `roll_video.mp4` files plus the stable
ONNX model and cards using `data/demo-assets.json`. Existing teammates can obtain them with `git pull`.
For the local demo, use `make env` then `THREADEYE_DETECTOR_PROVIDER=local_model make up`; no shared
database credentials are required. Supabase's `threadeye fetch-demo-assets` remains available for
older/incomplete checkouts with team cloud configuration.
