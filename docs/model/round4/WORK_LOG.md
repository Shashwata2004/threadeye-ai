# Renderer-matched line-scan follow-up

The user authorized fixing actual-renderer training data, reviewing independent thin-yarn examples already in Kaggle, and a two-epoch pilot measured on videos before any larger fine-tune. No scratch model or replacement source dataset is used. The installed baseline model stays unchanged unless all original final release gates pass.

## Timing and interruptions

This follow-up began 2026-11-04 17:39:37 UTC with a six-hour wall-time cap ending 23:39:37 UTC. The turn was interrupted after CPU preparation submission; GPU pilot had not been submitted. On continuation at 2026-11-05 00:59 UTC the CPU job had completed. The missed original deadline is retained in run.json. Remaining already-authorized pilot/conditional-final work has a separately recorded two-hour continuation cap, ending **2026-11-05 03:02:05 UTC (09:02 Dhaka)**. Do not silently reset it or begin training without enough time remaining.

## Actual renderer implementation

- `tools/simulator/make_roll_video.py` now exposes `render_fabric_view` and `apply_camera_effects`; the video generator and training generator call the same functions. DatasetSource flat-field normalization/colour transfer, RollRenderer, FabricDecor, selvage, board, drift, exposure blur/light/gain/noise run on target and clean examples.
- `ml/linescan_rendered.py` uses the existing private full AITEX training originals/masks from `threadeye-linescan-domain-r2`, verifying source and mask hashes. Other existing training domains use native labelled tiles through the same renderer. Renderer aliases map through the existing taxonomy, without relabelling classes for a better score.
- Every visible pixel donor, background and lighting-reference original/group is recorded. The **same reserved groups as round three** are kept out of training, so the existing frozen validation videos remain held out from fine-tuning. No final-test pixels enter data preparation.
- Sixty percent of strip examples align with a source strip, matching actual line-scan motion; the remainder include partial-edge camera views. Target labels follow exact renderer coordinates and clip to the camera crop. Actual rendered threads/wrinkles/stickers get non-defect labels; board/selvage remain hard negatives.
- Training frames are JPEG94 from the shared pre-encoding video raster; this does not reproduce H.264 compression. Hand occlusion is not added by this generator.
- Morphology audit of eligible broken-yarn originals: train AITEX 8 (1 thin-vertical), Moratuwa 8 (2 thin-vertical), Tianchi 330 (10 thin-vertical), WFDD 4 (0 thin-vertical). Validation has 3 thin-vertical Tianchi originals. This is a bounding-box morphology filter, not a claim that all are semantically identical to AITEX 006. AITEX subtype 006 still has **one** original; explicit views of it do not increase original count.

## Preparation preflight

- CPU `threadeye-linescan-round4-prepare/v1` completed 10,000 train / 1,000 validation frames. Local source/coordinate tests and 27 actual AITEX sample images passed, but the full contact sheet exposed printed-fabric backgrounds mixed into grey WFDD and Moratuwa scenes. **v1 was rejected before any GPU pilot.** Its report/previews are retained separately.
- Coherent-background correction restricts WFDD to the same fabric family when available and chooses one nearest clean appearance per scene. AITEX references use its fabric family. This prevents unrelated clean weaves creating colour quilts or extreme flat-field corrections.
- CPU v2 has that correction but repeatedly recreated expensive AITEX source profiles under the generic cache limit. It is superseded for performance; no GPU pilot uses it. Its timeout is bounded.
- CPU **v3** retains AITEX profiles and vectorizes nearest-clean lookup. It prepares **6,000 training frames** (3,000 target / 1,800 old replay / 1,200 clean) plus 1,000 validation frames. The 50/30/20 mixture remains exact. At approximately 01:48 UTC all 6,000 train / 1,000 validation frames finished; Kaggle is publishing the frozen output before local visual review. Its code snapshot predates later GPU-only edits, as intended.
- Active detached review process: `build/kaggle/round4/review-v3.log.pid`; log `review-v3.log`. Live CPU log: `preparation-v3-live.log`. Review must use preparation **v3**, not v1/v2. New previews are fetched without downloading full multi-GB training archives.

## Pilot and conditional final

- `scripts/run_rendered_linescan.py` wraps the existing checked controller for round4; it routes video downloads to frozen round3 preparation/v2 while using new round4 training data. Source checks now expand every background/reference group/original in provenance.
- GPU starts from the existing round-two checkpoint, learning-rate scale 0.1, batch 8, two epochs. No scratch initialization, mosaic, rotation or mixup. Every five batches keep 50/30/20.
- Input is **320x640**, large enough for all target camera frames at native pixel scale. Rectangular training overrides random resize so the base trainer cannot silently double the input. Replay can be resized; target/clean dimensions are checked before submission.
- Evaluate whole-strip and overlapping tiles at native 1x, with/without stitching, selected on validation videos. With a 320-high input the packed layout cannot stack two 248-high strips and duplicates ordinary tiles, so it is omitted. No thresholds/layouts are selected on regression/final-test outcomes.
- Pilot must meet the predeclared run.json gate on both GPU and laptop CPU: native precision >=85%, at least one correct broken yarn on the **original** linescan_roll, >=23/30 existing-regression TP, <=14 FP overall and <=1 FP on the original roll, and validation-video precision/recall/correct-broken recall at least the recorded prior baseline. This prevents full training based only on improved image scores or the already-known geometry fix.
- `submit(pilot)` requires visual approval matching preparation hash and coherent-background provenance. GPU verifies canonical prepared-report identity, raw annotations/provenance hashes, frozen video manifest identity and every regression input hash before evaluation.
- `supervise` waits for the pilot, measures all four regressions and four validation videos on CPU, writes PILOT_REPORT.md/pilot-result.json, and stops if the pilot gate fails. If it passes, it publishes only code/configuration for a final eight-epoch job from the original starting checkpoint, retaining 2/4/6/8. It then runs the original final release checks. Final-test labels stay closed during pilot work.
- Pilot/final notebook IDs are distinct (`...round4-pilot`, `...round4-final`). An active supervise process should be detached so later chat interruption does not lose orchestration. The v3 review completed at 01:50 UTC. Pilot v1 was submitted at 01:50:54 UTC; detached supervision and live log capture are active. Visual review is explicitly pilot-only; residual actual-renderer joins in Moratuwa/Tianchi and the broad curved AITEX 006 training example are documented in visual-review.json.
- Deadline and minimum time-to-start checks remain active. Final release/deployment requires the original 26/30, >=5/7 correct broken yarn, false-alert, separate validation/final-test and laptop-speed gates. A pilot alone cannot replace the app model.

## Verification so far

New tests exercise actual DatasetSource/RollRenderer use, camera-edge label bounds, all-background split isolation and video-specific pilot gating. Existing target-data, metadata repair, checkpoint-history and release tests remain included. Scoped Ruff and git diff checks are used. No business API/schema or historical decisions are changed.

Shared raster/camera extraction was checked bitwise against the former inline arithmetic, including selvage alpha and blur 0/1/3.2 pixels; proof: renderer-parity.json. All 10 scoped ML tests passed again before GPU submission. Private code input was refreshed and is ready.

## Completed pilot outcome

Pilot v1 completed two epochs. GPU and laptop CPU agree: regressions 10/30 TP, 169 FP, correct broken yarn 0/7; validation 55/120 TP, 82 FP, correct broken yarn 17/29. Pilot gate failed; no eight-epoch final job was submitted and final-test labels remain closed. Seven-defect raw diagnosis is saved in pilot-diagnosis.json. REPORT.md/result.json contain the scoped results, limitations and unchanged installed model hash. API8099/frontend3000 both responded HTTP200.
