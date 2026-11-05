# Line-scan round-three result

Release gates passed: False
Candidate model SHA256: `7ec6c7e727c30c222076c1ca3cbf51cab001001097c6589459fa5288fd71ac7b`
Current four videos are development regressions, not blind tests.

## Existing four regression videos

| Video | Original TP/FP | Round two TP/FP | New TP/FP/FN | Correct broken yarn | CPU / video |
|---|---:|---:|---:|---:|---:|
| linescan_roll | 4/0 | 5/2 | 5/0/2 | 0/2 | 0.77 |
| demo_basic_roll | 2/2 | 3/0 | 1/0/2 | 0/0 | 0.83 |
| demo_mixed_roll | 6/4 | 7/4 | 5/1/4 | 0/2 | 0.78 |
| demo_challenge_roll | 7/12 | 8/8 | 7/11/4 | 0/3 | 0.73 |

## Native image validation

| Model | Recall | Correct-class recall | Precision | Correct broken-yarn recall |
|---|---:|---:|---:|---:|
| baseline | 0.5034 | 0.4549 | 0.5508 | 0.3609467455621302 |
| round2 | 0.4818 | 0.4684 | 0.8818 | 0.388560157790927 |
| Round three | 0.7591 | 0.751 | 0.8744 | 0.7613412228796844 |

Old image thresholds are frozen production values; new thresholds were selected on this validation. This is a development comparison, not an independent test.

## New validation videos: production-pipeline comparison

| Video | Original TP/FP | Round two TP/FP | New TP/FP/FN | New correct broken yarn |
|---|---:|---:|---:|---:|
| val_0 | 16/24 | 17/30 | 17/19/12 | 1/3 |
| val_1 | 10/35 | 12/42 | 11/29/15 | 3/6 |
| val_2 | 20/16 | 20/32 | 22/24/17 | 7/12 |
| val_3 | 15/17 | 14/20 | 14/21/12 | 3/8 |

## validation

{
  "precision": 0.40764331210191085,
  "recall": 0.5333333333333333,
  "broken_right_recall": 0.4827586206896552,
  "false_alarms": 93,
  "broken_truth": 29,
  "tp": 64,
  "fp": 93,
  "fn": 56
}

## final_test

Not evaluated: validation gates failed. The four final-test ground-truth/media files were not opened for model evaluation; metadata-only normalization is documented in WORK_LOG.md. No final-test accuracy is claimed.

## Selected inference and overall dataset comparison

{
  "version": "linescan-round3",
  "inference": {
    "whole_strip": true,
    "pack": false
  },
  "infer_scale": 1,
  "postprocess": {
    "stitch_yarn": false
  },
  "thresholds": {
    "hole": 0.66,
    "stain": 0.86,
    "slub": 0.26,
    "broken_yarn": 0.14,
    "missing_yarn": 0.58,
    "knot": 0.84,
    "crease_mark": 0.2,
    "contamination": 0.76,
    "shade_bar": 0.15,
    "other_defect": 0.35,
    "sticker": 0.05,
    "loose_thread": 0.65,
    "wrinkle": 0.25,
    "hand": 0.3
  },
  "export_parity": [
    {
      "shape": [
        1,
        3,
        640,
        640
      ],
      "max_absolute_error": 6.699562072753906e-05
    },
    {
      "shape": [
        1,
        3,
        256,
        640
      ],
      "max_absolute_error": 8.106231689453125e-06
    }
  ]
}

| Model | Global recall | Correct-class recall | Precision | Correct broken-yarn recall |
|---|---:|---:|---:|---:|
| Original 44 epoch | 0.5515 | 0.5106 | 0.725 | 0.3436 |
| Round two | 0.5469 | 0.5034 | 0.7542 | 0.3216 |
| Round three | 0.3966 | 0.3514 | 0.6772 | 0.4714 |

Fine-tuning validation originals were seen by the starting checkpoints during older training. AITEX 006 still has one training original. Fresh final videos use non-AITEX official test donors because regression pools already used the AITEX test defects. Global results are advisory; they cannot conceal a line-scan failure.
Global test uses the original native tile evaluation protocol, without video tracking/stitching. Frozen videos retain identical pixels/truth/frame coordinates; expected-score serialization alone was repaired before restarted final training (old/new metadata hashes are in frozen_videos.json).

## Release blockers

- regression: fewer than 26/30 defects
- regression: fewer than 5/7 broken yarn correctly classified
- final_test: not evaluated because validation did not pass
- validation: recall below 85%
- validation: precision below 85%
- validation: correct broken-yarn recall below 80%
- native image validation: recall below 85%
- native image validation: correct broken-yarn recall below 80%

No production model was changed.

## Why this attempt did not qualify

The best image-validation checkpoint was epoch 6, not epoch 8. Native validation improved, but the production video pipeline did not: original four videos fell from 19/30 (original model) and 23/30 (round two) to 18/30. Correct broken-yarn detections stayed 0/7. Thus the intended line-scan improvement was not achieved.

### Seven missed broken-yarn defects

| Video | Defect | Diagnostic stage | Maximum correct-argmax broken-yarn score | Production threshold |
|---|---|---|---:|---:|
| demo_challenge_roll | 6 | tracking_or_geometry | 0.357634 | 0.14 |
| demo_challenge_roll | 8 | tracking_or_geometry | 0.674025 | 0.14 |
| demo_challenge_roll | 11 | tracking_or_geometry | 0.733217 | 0.14 |
| linescan_roll | 5 | no_usable_prediction | 0.003627 | 0.14 |
| linescan_roll | 7 | no_usable_prediction | 0.000048 | 0.14 |
| demo_mixed_roll | 4 | no_usable_prediction | 0.000327 | 0.14 |
| demo_mixed_roll | 7 | wrong_class | 0.006352 | 0.14 |

Three faults have no usable correct prediction, one is classified incorrectly, and three produce fragments that fail tracking/geometry association. All-visible-frame replay does not recover the missing seven; increasing sample frequency alone is insufficient. Lowering thresholds is not a demonstrated fix (the selected broken-yarn threshold was already 0.14). See candidate-diagnosis.json and raw frame traces in build/kaggle/round3/candidate-diagnostics.

### Data and rendering limitations

AITEX subtype 006 still has only one training original, represented by 157 variants. WFDD/Moratuwa/Tianchi broadened the class but have not established coverage of the thin vertical faults in these AITEX regression videos.
The target training generator uses native source-image sliding crops with noise/exposure. It does not pass those target examples through the complete DatasetSource/RollRenderer image path (flat-field normalization, colour matching, weave joining and moving camera frames). Only the validation/test videos use that complete renderer. Therefore the plan's renderer-matched target-training requirement remains incomplete. The image/video performance gap is observed; rendering mismatch is an identified, untested potential contributor, not a proven sole cause.
Fresh validation videos also use tiled YOLO sources, whereas existing regressions use single-column AITEX source rolls. These source/style differences must be represented explicitly in training and validation.
Of 93 CPU validation false alerts, 88 are unassociated with labelled truth/nuisance objects, three overlap wrinkles, one loose thread and one selvage. Unassociated does not prove that every region is visually defect-free; those regions need visual review before becoming hard negatives.

### Required next work before another training attempt

1. Use the actual production renderer to construct target training camera frames, including normalization and frame-edge motion, from training-only donor/background groups. Keep every donor and background out of validation when used in training.
2. Review existing Kaggle training originals for independent thin vertical broken-yarn examples matching subtype 006; do not substitute many transformations of the singleton for new source diversity or relabel missing-yarn/crease images merely to improve a score.
3. Review unassociated video false alerts and add verified renderer-matched hard negatives. Diagnose fragment association on validation without tuning the production threshold on regression/final-test videos.
4. Repeat pilots on the corrected data before another bounded final fine-tune. No new training is started near this run's six-hour deadline.

### Operational outcome

The candidate remains staged and rejected for deployment. Laptop CPU speed passed on all measured regression/validation videos (0.22–0.83x video duration); accuracy is the blocker. PyTorch/ONNX export parity passed. The installed model and all historical inspection decisions remain unchanged. The four final-test videos remain unevaluated.
