# Data & AI Provenance

This covers the **Data & AI Provenance** submission section.
Rule (PLAN.md §2, brief §11): everything simulated is labelled as simulated; sample or fictional data is
marked "sample data"; no fabricated metrics.

## AI in the product
| Component | Status | Notes |
|---|---|---|
| SimulatedDetector | Implemented | Reads the simulator's answer key. **Not AI**; separately labelled on screens, checks and reports. |
| ApiDetector | stub, not implemented | No external AI API is called |
| LocalModelDetector | Implemented, YOLOX-S, 44 epochs | Real inference via ONNX Runtime CPU. Video remains simulated. Model cards: `backend/threadeye/data/model/`; detailed sources and split policy: `ml/DATASETS.md`. Confidence is not calibrated and remains null. |

## Datasets
| Dataset | Origin | Licence | Where | Status |
|---|---|---|---|---|
| AITEX Fabric Image Database | AITEX (Spain); "A Public Fabric Database for Defect Detection Methods and Results", *Autex Research Journal* | **To be verified** (PLAN.md Q2: may derived video be redistributed publicly?) | Read by `tools/simulator/` (`--source aitex`); not in this repo | Open question |
| Simulated sample roll | Our simulator (`tools/simulator/make_roll_video.py`, realistic mode, AITEX fabric 02, seed 11): 13.1 yd, 8 defects, 17 non-defect distractions; expected 10 points, 46.45, FAIL | Derived; same as above | `data/sample_roll/`: CSV/JSON and preview in git, `roll_video.mp4` kept out of git until Q2 is answered (SHA-256 in `SHA256SUMS`) | **SIMULATED** |
| Current line-scan roll | AITEX fabric 02, seed 11, 7 known faults; source group excluded from training | Derived; AITEX redistribution question above remains open | `data/linescan_roll/`, evaluation manifest and hashes | **SIMULATED**, repeatedly used development/regression fixture; not a fresh blind test |
| CI browser-test roll | Rendered in CI by the same simulator in `synthetic` mode (code-drawn fabric, no dataset), 5 m, seed 3 | Ours | `data/ci_roll/` (generated, not committed) | **SIMULATED** |
| Micro-fixture roll | Synthetic CSV/JSON written by `scripts/make_micro_fixture.py` (no images) | Ours | `backend/tests/fixtures/micro_roll/` | **SYNTHETIC test data** |

## Sample data
| Data | Status |
|---|---|
| Demo user accounts (one per role) | Created only when `THREADEYE_SEED_DEMO_USERS=true`. The password comes from the environment, not from code. |
| Mills and buyers | Fictional, flagged `is_sample_data`, shown with a "SAMPLE DATA / নমুনা তথ্য" badge; a lot from a sample mill or buyer is flagged too |
| Inspections | Video is simulated (`is_simulated`); provider snapshot separately records whether detections are simulated or real model inference. |
| Reviewed-label exports | Saved images plus COCO annotations and inspector decisions; source groups remain together, split is unassigned, and review is required before training. Rejected boxes do not imply that an entire image is clean. No automatic retraining occurs. |
| Demo reset | Explicit, opt-in sample-delivery archive. Evidence and audit records remain; unmarked real deliveries are not archived. |

## Fonts
| Font | Licence | Where |
|---|---|---|
| Noto Sans (Regular, Bold) | SIL Open Font License 1.1 | `frontend/src/fonts/`, `backend/threadeye/reports/fonts/` |
| Noto Sans Bengali (Regular, Bold) | SIL Open Font License 1.1 | same |
| Noto Sans Mono (Regular) | SIL Open Font License 1.1 | `frontend/src/fonts/` |

Fonts are self-hosted, with no CDN, so the edge box works offline.

## Third-party software
Key runtime libraries (full lists: `backend/uv.lock`, `frontend/pnpm-lock.yaml`):
- Backend: FastAPI, Starlette, Pydantic (MIT); SQLAlchemy, Alembic (MIT); psycopg (LGPL-3.0, used unmodified as a library); argon2-cffi (MIT); fpdf2 (LGPL-3.0, used unmodified); uharfbuzz (Apache-2.0); PyYAML (MIT).
- Frontend: Next.js, React (MIT); next-intl (MIT); TanStack Query (MIT); openapi-fetch / openapi-typescript (MIT); MSW (MIT); Tailwind CSS (MIT).
- Infrastructure: PostgreSQL (PostgreSQL Licence); Caddy (Apache-2.0).

Training framework recorded by the model card: YOLOX (Apache-2.0), not Ultralytics. Model/runtime and
dataset licence questions are distinct: source-specific credits, mirrors, non-commercial restrictions
and unresolved terms are maintained in `ml/DATASETS.md`. Do not treat availability on a mirror as
proof of permission for public redistribution or commercial deployment.
