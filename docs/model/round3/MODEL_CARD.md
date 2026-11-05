# Line-scan round-three candidate

**Rejected for deployment.** Training and CPU verification completed; regression/video accuracy gates failed. Final-test evaluation was not run. See REPORT.md.

Model SHA256: `7ec6c7e727c30c222076c1ca3cbf51cab001001097c6589459fa5288fd71ac7b`

Model metadata SHA256: `e9ad1402cdc8ab2b7edad2bea960f24996ee4e24c615cb14aa37a543e8001b20`

Prepared input: `shashwatanandi2004/threadeye-linescan-round3-prepare/v2`; preparation SHA256: `5b177a8771ce1b77d3779bba2fe3e1e6379df3401173391a44e580e1e2145d02`.

Frozen video manifest SHA256: `88f0096914e21a263d5a1e17f47168c206bf2edbb0f0a2f589a2866bbc14117d`.

Validation-selected model metadata (thresholds are uncalibrated detector scores):

```json
{
  "framework": "YOLOX",
  "yolox_commit": "6ddff4824372906469a7fae2dc3206c7aa4bbaee",
  "runtime_versions": {
    "python": "3.13.15",
    "torch": "2.11.0+cu128",
    "numpy": "2.1.3",
    "onnxruntime": "1.31.1"
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
  ],
  "size": "s",
  "input": [
    640,
    640
  ],
  "classes": [
    "hole",
    "stain",
    "slub",
    "broken_yarn",
    "missing_yarn",
    "knot",
    "crease_mark",
    "contamination",
    "shade_bar",
    "other_defect",
    "sticker",
    "loose_thread",
    "wrinkle",
    "hand"
  ],
  "version": "linescan-round3",
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
  "postprocess": {
    "stitch_yarn": false
  },
  "infer_scale": 1,
  "preprocessing": "native BGR, pad 114; inference layout and pixel scale selected only on held-out validation video groups",
  "starting_checkpoint": "/kaggle/input/notebooks/shashwatanandi2004/threadeye-linescan-r2/runs/threadeye_s/latest_ckpt.pth",
  "selected_checkpoint": "/kaggle/working/round3/final/final/epoch_6_ckpt.pth",
  "split_manifest_sha256": "19f12c9d49d1ce10b13812e672d1502c131316c3a889affd4e4ff5b20a98808c",
  "frozen_video_manifest_sha256": "45714a6e18f21cca61e8391849f71a1afa77f218ce76944fca6946b72727f2d6",
  "video_manifest_hash_format": "canonical sorted JSON",
  "run_status": [
    "training: finished all epochs",
    "validation selected epoch checkpoint"
  ],
  "purpose": "simulated native line-scan; deployment requires independent release gates",
  "train_parameters": {
    "seed": 202611043,
    "lr_scale": 0.1,
    "epochs": 8,
    "batch": 8,
    "buckets": {
      "target": 0.5,
      "replay": 0.3,
      "clean": 0.2
    }
  },
  "inference": {
    "whole_strip": true,
    "pack": false
  },
  "validation_video_metrics": {
    "precision": 0.41025641025641024,
    "recall": 0.5333333333333333,
    "broken_right_recall": 0.4827586206896552,
    "false_alarms": 92,
    "broken_truth": 29,
    "tp": 64,
    "fp": 92,
    "fn": 56,
    "seconds": 19.921675507000145
  }
}
```

Training sources, original/variant counts and exclusions: [preparation.json](preparation.json). Source isolation and validation limitations: [WORK_LOG.md](WORK_LOG.md). Deployment eligibility and measured CPU/video results: [REPORT.md](REPORT.md). The model is a candidate until every release gate passes; no business decision is automated by this card.
