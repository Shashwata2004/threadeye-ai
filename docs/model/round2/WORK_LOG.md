# Second line-scan training experiment — 4 November 2026

[Private Kaggle run](https://www.kaggle.com/code/shashwatanandi2004/threadeye-linescan-r2)

## Why another experiment

The first additional 8 epochs improved the overall held-out tile report slightly but increased
false alarms on the original and mixed line-scan videos. Most extra false alarms overlapped normal
selvage/pin-hole regions. Long broken-yarn faults remained missed. The 52-epoch candidate did not
replace the app model. Round two starts again from the known 44-epoch checkpoint, not that candidate.

## What changes

- Reuse the existing Kaggle packed train/val/test dataset and `threadeye-train-2/latest_ckpt.pth`.
- Frozen packed manifest SHA-256 remains
  `19f12c9d49d1ce10b13812e672d1502c131316c3a889affd4e4ff5b20a98808c`.
- Raw originals come **only** from that manifest's AITEX train membership: 122 source images,
  including 83 known-clean images. Original pixels and their masks are hashed and checked.
- Synthetic positives paste **real mask-defined defects** onto clean train fabric at native
  line-scan scale. They are not drawn from the demo test video's missed defects.
- Normal selvage, pin holes, wavy edges and board use the **same renderer functions as the videos**.
  Known-clean examples teach these as background. Separate loose-thread/wrinkle/sticker examples
  retain their correct non-defect labels. Real defects and handling wrinkles are not relabelled as
  one another.
- Add 8,000 native 640×248 images: 4,800 positives and 3,200 edge/non-defect examples. Planned positive
  balance is 2,160 broken yarn / 720 missing yarn / 1,200 crease / 720 slub. These are augmented
  variants, not that many independent physical defects. Crease donors remain limited to two train
  source files; no claim of broad crease coverage is made.
- Original training examples remain. Mosaic and rotations are disabled, color perturbation is
  reduced, and the learning rate is 10% of the base schedule. Eight fine-tuning epochs requested.
- Thresholds are chosen on validation. Defect thresholds cannot fall below the original model's
  thresholds; non-defect thresholds cannot rise above them. This guards the loose-thread/nuisance
  threshold drift seen in round one. It does not guarantee improved test results.
- Val/test pixels and labels are unchanged. Current demo corrections remain test-only.

## Checks performed before launching

- 25 ML tests passed, including source/hash/split rejection, native-strip box clipping, preservation
  of existing annotations, validation-threshold bounds, and the earlier candidate comparison checks.
- Generated and inspected 40 labelled previews, including all four target classes and clean edges.
  Preview annotations are in a separate ignored build directory; labels are not painted into the
  actual training images.
- Private input dataset uploaded. The new GPU notebook was confirmed RUNNING with private metadata,
  existing packed data and the 44-epoch source attached. No base dataset was rebuilt.
- Kaggle expanded the raw-source archive during upload. The first launch stopped before training
  because it expected a tar file. Version 2 handles the expanded directory as well; its native-data
  generation was observed passing 1,000/8,000 examples with source/hash checks intact.

## Continuation

`run.json` selects the round-two notebook, output folder and private CPU comparison notebook.
The collector waits for training/export, then submits the CPU comparison against the same four
fixed videos. Results are written to `COMPARISON.md` in this folder, preserving round-one results.
The app continues to use its existing model until a better candidate is actually demonstrated.

```bash
backend/.venv/bin/python scripts/collect_kaggle_candidate.py \
  --run-config docs/model/round2/run.json --submit-cloud-evaluation
```

The running collector temporarily inhibits automatic sleep and releases that inhibitor when it exits.
Training and cloud comparison completed. The local collector was no longer running after the
computer restart; collection was resumed and the candidate/model hashes verified on November 4,
2026 at 17:33 Dhaka. Results are in COMPARISON.md and candidate-comparison.json.

Across the four simulated videos, detections improved from 19/30 to 23/30 and false alerts fell
from 18 to 14, although the original video gained two false alerts. The unchanged overall test
recall fell from 55.15% to 54.69%, correct-class recall from 51.06% to 50.34%, and broken-yarn
recall from 34.36% to 32.16%. Nuisance false detections also increased. The candidate did not pass
the promotion criteria. It is staged for review; the app's baseline model hash remains unchanged.
