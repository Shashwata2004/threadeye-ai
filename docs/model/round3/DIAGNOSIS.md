# Round-three diagnosis

Actual baseline and round-two ONNX inference, six layouts/scales, all visible frames of the seven broken-yarn faults. No DB changes.

| Model | Video / defect | Current-mode cause | Max broken-yarn argmax score | Threshold |
|---|---|---|---:|---:|
| baseline | linescan_roll / 5 | no_usable_prediction | 0.0083 | 0.35 |
| baseline | linescan_roll / 7 | no_usable_prediction | 0.0004 | 0.35 |
| baseline | demo_mixed_roll / 4 | no_usable_prediction | 0.0008 | 0.35 |
| baseline | demo_mixed_roll / 7 | threshold | 0.0177 | 0.35 |
| baseline | demo_challenge_roll / 6 | tracking_or_geometry | 0.3852 | 0.35 |
| baseline | demo_challenge_roll / 8 | tracking_or_geometry | 0.7116 | 0.35 |
| baseline | demo_challenge_roll / 11 | tracking_or_geometry | 0.6386 | 0.35 |
| round2 | linescan_roll / 5 | threshold | 0.0378 | 0.35 |
| round2 | linescan_roll / 7 | no_usable_prediction | 0.0008 | 0.35 |
| round2 | demo_mixed_roll / 4 | no_usable_prediction | 0.0020 | 0.35 |
| round2 | demo_mixed_roll / 7 | threshold | 0.0202 | 0.35 |
| round2 | demo_challenge_roll / 6 | threshold | 0.1850 | 0.35 |
| round2 | demo_challenge_roll / 8 | tracking_or_geometry | 0.7925 | 0.35 |
| round2 | demo_challenge_roll / 11 | tracking_or_geometry | 0.8231 | 0.35 |

The challenge faults span much of the cloth width. The model emits overlapping horizontal fragments; treating any intersection as a hit would overstate recall. Diagnostic association was corrected to the production IoU/centre-distance matching rule before drawing conclusions.

Opt-in overlap-only yarn stitching improved the full challenge replay from 7 TP / 12 FP to 9 TP / 1 FP on baseline weights. The first three video results were unchanged. This experimental setting is OFF for existing model cards and has not been deployed.

Raw predictions and per-frame class vectors remain in ignored build output. Source-group training/validation isolation and thin-box projection tests passed. The four frozen original videos are regression data, not a blind final test.
