# Line-scan model improvement — 4 November 2026

This work reuses the existing Kaggle model and data. It is not training from scratch.

## Verified starting point

- Kaggle `shashwatanandi2004/threadeye-train-2`: COMPLETE, 44 epochs, YOLOX-S.
- Its ONNX SHA-256 matches the running model exactly:
  `02de7b97544dc5483b7da95972141c329b0fbc8c1bb495246d03165c4a796037`.
- Existing `threadeye-pack-dataset` and `threadeye-patch-dataset`: COMPLETE.
  The old full build's latest status is CANCEL_ACKNOWLEDGED, but its previously saved output
  remains available through the completed packed dataset. No rebuild of the full dataset was needed.
- Packed manifest downloaded and frozen by SHA-256. Its AITEX originals are 122 train and 111 test
  files. Fabric 02 occurs only in test; fabric 03 has both train and test originals, so a fabric-03
  demo is **not** claimed to be an entirely unseen fabric.
- Existing private code and helper scripts were inspected. No credentials were copied into the
  new add-on dataset or committed source files. Existing private inputs stay private.

## Authorized training run

[Kaggle run](https://www.kaggle.com/code/shashwatanandi2004/threadeye-line-scan-fine-tune-from-epoch-44)

- Private notebook, two T4 GPUs, version 1; real training progress observed.
- Starts explicitly from `threadeye-train-2/runs/threadeye_s/latest_ckpt.pth`.
- Reuses all existing packed train/val/test data, without changing split assignments.
- Adds 1,600 train-only derived images: cropped strips, limited contrast/brightness/noise/blur,
  targeted toward broken yarn, missing yarn, crease and slub. All visible labels, including
  nuisance classes, follow the crops. Some second strips are defect-free train examples.
- Original training examples remain; this is an add-on, not a replacement dataset.
- Eight requested fine-tuning epochs, quarter learning rate, reduced mosaic and fixed 640 scale.
  Training budget 3.5 hours; full notebook timeout six hours, including test and export.
- Frozen-manifest identity checked before training. Validation/test files are copied unchanged;
  operating thresholds continue to be selected on validation only.
- A separate checkpoint-backup prefix prevents overwriting the old training backups.
- Corrections from the current demo inspections are **not** used as train labels: those images
  belong to held-out test fabric 02. Their export remains available for review, not leakage into train.

The running app model has not been replaced. Training success or improved accuracy is not yet claimed.

## New demo videos and challan

Sample challan `CH-DEMO-LINESCAN-20261104` was registered through the audited receiving API.
No inspections or supervisor decisions were fabricated. Open the roll inspection screen, choose
the dataset matching the roll below, and load its roll code.

| Roll code | Dataset/video | AITEX fabric | Scenario |
|---|---|---|---|
| TE-000007 | demo_basic_roll | 02 | Fewer defects, mild noise |
| TE-000008 | demo_mixed_roll | 02 | Mixed defects and distractions |
| TE-000009 | demo_challenge_roll | 03, test originals only | More defects, stronger noise and faster motion |

All are 12-metre simulated rolls, nominal 13.123 yd and 59.06 in, with the same line-scan file contract:
MP4, roll metadata, frame positions, ground truth, nuisances and preview. Source fabric 03's photographed
board margin was cropped before rendering. The three source pools contain respectively 32/26/47
test-only original images and share no original file with each other. Ground-truth previews are
evaluation material; the live cutting map continues to use unannotated video pixels.

These are new arrangements of existing held-out images, **not** a new blind physical-fabric test or
factory footage. The original `linescan_roll` has not been regenerated. Individual source hashes and
the packed-manifest hash are recorded in each `evaluation_manifest.json`.

## Evaluation and continuation

- Baseline replay: `docs/model/linescan-baseline/`; resumes only when model, card, video/CSV hashes
  and inference settings match. CPU inference uses two threads for both model versions.
- Collector: `scripts/collect_kaggle_candidate.py`, detached process. Current phase is in
  `docs/model/training-state.json`; logs are under ignored `build/kaggle/`.
- On Kaggle completion it downloads the candidate, checks completion/manifest identity, replays
  the same four videos and writes `docs/model/candidate-comparison.json`.
- Candidate review requires fewer roll misses without more roll false alarms or lower per-roll
  true detections; overall recall/class recall must not regress, precision may fall at most two
  percentage points, and overall false alarms may rise at most one per 100 tiles. Broken-yarn and
  crease recall and nuisance rejection must not regress. Different evaluation inputs are rejected.
  Model-only verdict disagreements and total roll-score error must not increase either.
- The collector stages results; it **does not activate** or publish an unreviewed model.
  Installation and final model/report updates remain pending actual comparison results.

To resume collection if this laptop was shut down:

```bash
backend/.venv/bin/python scripts/collect_kaggle_candidate.py --submit-cloud-evaluation
```

Overnight continuation: the worker now uses `--submit-cloud-evaluation`. A private CPU comparison
notebook is submitted **after** the GPU notebook finishes, reusing that saved output and the frozen
four-video bundle. A premature dependency submission showed that Kaggle drops a first-ever notebook's
unfinished output; that initial CPU attempt stopped without training anything. The GPU training run
is unaffected. The worker will submit the corrected follow-up only when its input exists, and falls
back to local comparison if cloud submission/evaluation fails. The final Bangla report is
`docs/model/COMPARISON.md`, also saved in the private comparison notebook's output when successful.

The continuation worker temporarily inhibits automatic sleep while it runs. The inhibitor is released
when the worker exits; no permanent power setting is changed. Shutting down the laptop still stops
local monitoring; Kaggle training itself runs independently.

Reproduce video generation with the frozen manifest (existing output directories are protected):

```bash
backend/.venv/bin/python scripts/build_demo_rolls.py \
  --manifest build/kaggle/existing/packed-metadata/threadeye_packed/manifest.csv
```

## Validation completed

- 22 ML tests passed: existing dataset/split tests, new crop/provenance/reproducibility checks,
  held-out donor rejection and candidate comparison guards.
- 15 existing impact-service unit cases passed after adding optional inference thread control.
- New Python files pass Ruff; training/augmentation modules compile.
- All three videos pass the dataset validator with no errors. Their line-scan geometry differs
  from the validator's original area-camera fixture, producing an expected geometry warning.
- Representative rendered video frames inspected; no answer-key boxes painted into the videos.
- Baseline completed: original roll 4 TP / 0 FP / 3 FN; basic 2 / 2 / 1; mixed 6 / 4 / 3;
  challenge 7 / 12 / 4. These 19 TP / 18 FP / 11 FN are for the simulated suite, not the overall
  tile benchmark. In particular, the new patterned challenge roll exposes false-alarm weaknesses.
- All three new videos are listed by the running API; authenticated byte-range playback was checked.
  Re-running challan registration keeps exactly three rolls instead of duplicating them.
