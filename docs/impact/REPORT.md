# ThreadEye impact evidence

**SIMULATED VIDEO / REAL MODEL INFERENCE. Laboratory replay; factory impact has not been measured.**

Measured at (UTC): 2026-11-03T14:05:45.039954+00:00. Code revision: `3492ec59d82a61fa96ffe2fb75188abff327b344`.
Local changes may exist; implementation hashes in evidence.json identify the code used for this run.
Dataset: `linescan_roll` (aitex-fabric-02). Profile: `Simulator parity`.

## Measured detection results

| Metric | Result |
|---|---:|
| True defects found | 4 / 7 |
| False alarms after pipeline filtering | 0 |
| Recall | 57.14% |
| Precision | 100.00% |
| Headless processing, including model setup | 43.461 s |
| Source video duration | 51.789 s |

Processing time excludes browser, network, database writes, human review and reporting. It is not inspection time saved or a production throughput measurement.
Matching uses the existing roll evaluator: IoU > 0.3 OR centres within 3 cm, greedy one-to-one. Class accuracy is separate. The tile benchmark uses a different matching rule.

## Decision risk: model detections versus answer-key oracle

Auto-confirm detections without human corrections. A replay, not a production decision.

| Replay | Points | Points / 100 sq yd | Verdict |
|---|---:|---:|---|
| Model detections | 4 | 18.58 | PASS |
| Answer-key oracle | 9 | 41.8 | FAIL |

The oracle is an evaluation reference, not a measured manual-inspection baseline. The model-only verdict cannot serve as an autonomous release decision; inspector review remains necessary.

Missed defects: #2 crease_mark at 4.291 yd; #5 broken_yarn at 10.468 yd; #7 broken_yarn at 12.853 yd

## Human and business impact

**Not measured:** manual versus assisted inspection time, reduction in human misses, usable-fabric gain and financial loss reduction. No savings claim is supported yet.

## Limits and reproduction

One short, simulated roll is a regression fixture; it has been used repeatedly during development. Its source fabric is held out of training. This is not a fresh blind test or evidence of factory-wide impact.
Bounding boxes do not prove cutting/yield improvement. No monetary value is assigned to a missed defect.

Run `make impact` from the repository root. See `PILOT_PROTOCOL.md` for paired human measurements. Hashes, machine details, evaluation output and optional pilot-input hash are in `evidence.json`.
