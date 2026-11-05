# Renderer-matched two-epoch pilot

Improvement gate passed: False

| Dataset | TP | FP | FN | Correct broken yarn |
|---|---:|---:|---:|---:|
| linescan_roll | 2 | 16 | 5 | 0/2 |
| demo_basic_roll | 1 | 125 | 2 | 0/0 |
| demo_mixed_roll | 3 | 2 | 6 | 0/2 |
| demo_challenge_roll | 4 | 26 | 7 | 0/3 |
| val_0 | 10 | 19 | 19 | 1/3 |
| val_1 | 9 | 38 | 17 | 4/6 |
| val_2 | 20 | 9 | 19 | 6/12 |
| val_3 | 16 | 16 | 10 | 6/8 |

Native image validation: {"precision": 0.8698, "recall": 0.5465, "broken_right_recall": 0.5506958250497018}

## Improvement blockers

- pilot: correct broken yarn on original videos did not meet the predeclared improvement condition
- pilot: regression detections retained did not meet the predeclared improvement condition
- pilot: regression false alerts did not meet the predeclared improvement condition
- pilot: original-video false alerts did not meet the predeclared improvement condition
- pilot: original-video correct broken yarn did not meet the predeclared improvement condition
- pilot: video validation precision did not meet the predeclared improvement condition
- pilot: video validation recall did not meet the predeclared improvement condition

Final-test labels were not evaluated. The production model and historical inspections remain unchanged.
