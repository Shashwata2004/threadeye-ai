# Line-scan round three

Budget began 2026-11-04 11:43:11 UTC; deadline 17:43:11 UTC (23:43 Dhaka). Interruptions do not reset it.

## Completed before GPU submission

- Real baseline and round-two inference: 36 combinations across whole-strip, overlapping tiles and packed tiles at 1x/2x. All seven previously missed broken-yarn defects have raw, threshold, geometry, filtering and sampled/all-frame evidence. See `DIAGNOSIS.md` and `diagnosis.json`.
- Identified overlapping long-yarn fragments. Optional geometric stitching joins overlapping, collinear same-class boxes, preserving the maximum existing score. It is disabled for the installed model. Full-video baseline experiment improved the challenge regression from 7 TP / 12 FP to 9 TP / 1 FP; the other three baselines stayed unchanged. This does not pass release gates.
- Frozen preparation version `shashwatanandi2004/threadeye-linescan-round3-prepare/v2`: 10,000 training and 1,000 validation images. Exact training buckets 5,000 target / 3,000 replay / 2,000 clean. See `preparation.json` for original/group/variant/class counts. Training has 2,971 distinct original identifiers; validation has 164. All group and packed source split checks passed.
- Excluded derived AITEX-paste and synthetic nuisance replay whose donor lineage is incomplete. Kept correctly labelled new nuisance examples.
- Visually inspected 23 labelled previews, including the singleton AITEX 006 original and Moratuwa broken-yarn examples. Boxes remain aligned with their native source pixels and frame-edge clipping. AITEX 006 contributes 157 variants from **one** original, all in training; this is not 157 independent examples.
- Four validation and four final-test videos frozen before training, with source groups and per-file hashes in `frozen_videos.json`. Fresh final-test defect originals come from official packed test WFDD/Moratuwa/Tianchi sources: the four existing regressions exhausted the AITEX test defect donor pool. Existing regressions are not blind tests. New validation is held out from fine-tuning, but starting checkpoints have seen its original packed training sources.
- Corrected local Kaggle orchestration: the installed CLI parses version suffixes but omits them from status/output requests. Explicit SDK `version_label=v2` now pins completed data rather than waiting on a newer preparation revision. Downloads check HTTP status and never log signed URLs.

## GPU run

Submitted at 13:08:28 UTC, private notebook `shashwatanandi2004/threadeye-linescan-round3-train`, same pinned training image and T4 environment. Kaggle returned RUNNING and retained all four source notebooks. Submission/RUNNING alone is not evidence that an epoch has trained; epoch logs and saved metrics must confirm it.

- A: original 44-epoch checkpoint, learning-rate scale 0.1, two epochs.
- B: same checkpoint, scale 0.3, two epochs.
- C: round-two checkpoint, best eligible A/B scale, two epochs.
- Every eight-image batch has four targets; five batches give exactly 50/30/20. No mosaic, rotation or mixup.
- Select using validation precision >=85%, highest correct broken-yarn recall, fewer false alerts, then runtime. Stop before final training if all pilots have zero eligible correct broken-yarn recall.
- If eligible, fine-tune from the winning **starting checkpoint**, save epochs 2/4/6/8 and select by validation. Export checks real-pixel PyTorch/ONNX parity at two input shapes.
- Inference layout, scale and stitching selected on new validation videos, with production sampling, nuisance filtering and tracking. Final-test videos are opened only after video validation gates pass. Original overall test is advisory and is evaluated after selection.

## Release

The collector measures the candidate on the same laptop CPU and all four existing regressions. Every requested accuracy, false-alert, broken-yarn and speed gate must pass. Candidate artifacts and model-card hashes must match measured artifacts. Conditional activation keeps a complete old model-directory backup and prevents the demo downloader from overwriting a validated local candidate. Historical inspections and business decisions are never rewritten.

At this point no candidate has been installed. See `state.json` for current state and, once available, `REPORT.md` / `result.json` for measured results.

## First measured results, 13:20 UTC

Pilot A completed two epochs and produced finite training losses. Native image validation: recall 71.33%, correct-class recall 70.52%, precision 86.46%, correct broken-yarn recall 70.41%. This qualifies for the pilot precision gate but does **not** meet the final 85% recall / 80% broken-yarn release gates.

The same 1,000 native validation images were also measured locally with the original and round-two ONNX models and their existing frozen thresholds:

| Model | Recall | Correct-class recall | Precision | Correct broken-yarn recall |
|---|---:|---:|---:|---:|
| Original 44 epochs | 50.34% | 45.49% | 55.08% | 36.09% |
| Round two | 48.18% | 46.84% | 88.18% | 38.86% |
| Pilot A | 71.33% | 70.52% | 86.46% | 70.41% |

Pilot thresholds were selected on this validation set; old thresholds stayed fixed. This is a development comparison, not a controlled threshold ablation or independent test.

## Pilot selection, 13:32 UTC

| Pilot | Starting checkpoint | LR scale | Recall | Precision | Correct broken-yarn recall | False alerts |
|---|---|---:|---:|---:|---:|---:|
| A | Original 44 epochs | 0.1 | 71.33% | 86.46% | 70.41% | 83 |
| B | Original 44 epochs | 0.3 | 67.03% | 86.31% | 63.12% | 79 |
| C | Round two | 0.1 | 76.45% | 88.75% | 75.54% | 72 |

All three passed the pilot precision condition and have non-zero correct broken-yarn recall. C wins the predeclared ranking. Eight-epoch final fine-tuning began from the original round-two checkpoint, **not** from C's already fine-tuned output. Epoch 2/4/6/8 validation and production video gates remain pending.

## Final-run recovery and metadata repair, 13:55 UTC

Two preflight gaps were found during final training and corrected:

1. At the pinned YOLOX commit, `save_history_ckpt` writes history only inside inline evaluation. Inline evaluation had deliberately been disabled. The initial final run (`train/v1`) cannot supply the required four-epoch comparison and is excluded from candidate selection. An explicit `Trainer.after_epoch` subclass now saves 2/4/6/8 independently of evaluation. A regression test exercises all eight epochs and confirms those four saved names. The pinned training entry point calls the overridden `Exp.get_trainer`.
2. The renderer calculated expected score from unrounded dimensions but serialized rounded length/width. A validation video's expected score differed by 0.03. Only `expected_score.points_per_100_sq_yd` / its corresponding verdict were normalized to the already serialized geometry. All four validation videos now pass the complete dataset contract. **No video pixels, truth labels, nuisance labels, frame positions or geometry were changed.** Final-test metadata was normalized without opening its truth/media files. `frozen_videos-original.json` preserves the initial manifest; `frozen_videos.json` records old/new metadata hashes and the deterministic repair before restarted final training.

The measured three pilots used the same training images and validation labels and remain valid. `pilots-recovery.json` preserves their measured results and source job. Exact original log-prefix evidence matching its SHA256 is in `build/kaggle/round3/gpu-pilot-evidence.log`.

Recovery `train/v2` stopped **before training** because the frozen-manifest check compared differently ordered JSON keys. Parsed manifests, every video/truth hash and metadata values were identical. Canonical sorted JSON now gives the same identity locally and on Kaggle (`45714a6e18f21cca61e8391849f71a1afa77f218ce76944fca6946b72727f2d6`). No identity check was removed.

Recovery `train/v3` began final epoch 1 at 13:55:17 UTC, reusing completed pilots and starting again from the selected original round-two checkpoint. It must retain and validate all four requested checkpoints. The six-hour deadline is unchanged. No candidate has been installed.

Validation so far: 14 backend provider/coordinate/activation tests, 23 runner/evaluation/decision tests and eight data-mixture/leakage/release/history/metadata tests passed. New orchestration/training files pass scoped Ruff checks. The older `scripts/measure_impact.py` has pre-existing lint findings under the root lint configuration; its model evaluation behavior is tested separately.

## Final measured outcome and close-out

Training v3 completed and the detached collector finished CPU verification at 14:39:29 UTC. No model was activated. The user resumed at 17:22 UTC; post-training ROI diagnosis and report correction finished before the unchanged 17:43 UTC deadline. No additional training was launched.

- Best checkpoint: epoch 6. Native validation recall 75.91%, precision 87.44%, correct broken-yarn recall 76.13%.
- Existing four video regressions: 18/30 TP, 12 FP, correct broken yarn 0/7. Original model: 19/30 TP; round two: 23/30 TP.
- New validation videos on laptop CPU: 64/120 TP, 93 FP, precision 40.76%, recall 53.33%, correct broken yarn 14/29 (48.28%).
- CPU duration ratios 0.22–0.83; speed passed. Export parity passed. No inference layout/scale/stitch option met video validation precision.
- Final-test evaluation was deliberately not run. Earlier release reasons incorrectly described missing final-test metrics as low scores; code and reports now explicitly say not evaluated because validation failed.
- Selected-model diagnosis accounts for all seven original broken-yarn misses: three no usable predictions, one wrong class, three tracking/geometry fragments. Full results: candidate-diagnosis.json.
- The complete simulator rendering path was used for validation/test videos, but target training examples were native source crops with noise/exposure. The plan's fully renderer-matched target-frame requirement remains incomplete. This is an implementation/data limitation, not a successful execution of that requirement. The observed image/video gap alone does not prove which rendering operation caused it.
- Full A/B/C saved pilot reports were recovered and exactly match the reused summaries (pilots.json). Forty-five scoped unit tests passed; new pipeline/orchestration files pass Ruff, and git diff --check passes.
- Activation dry-run correctly rejected this candidate. Installed model SHA remains 02de7b97544dc5483b7da95972141c329b0fbc8c1bb495246d03165c4a796037. API8099 health and frontend3000 both returned HTTP200. No historical inspection, business decision or shared model blob was modified.

This attempt did not achieve the requested line-scan improvement. REPORT.md states measured failures, missing data/rendering work and the unevaluated final-test status.
