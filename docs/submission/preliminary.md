# ThreadEye AI — preliminary submission draft

This is a reviewable draft of the current implementation, not proof that an earlier submission was filed.
Repository publication and release publishing are outside the owner's current authorization.

## 1. Basics

ThreadEye AI — কাপড় পরীক্ষার স্মার্ট সহকারী. IndustrySphere AI → Quality Vision.
Owner: Shashwata Nandi and the ThreadEye AI team. Add the final team roster and registration ID from the competition dashboard.

## 2. Problem

Receiving inspectors in garment factories must find, grade and document fabric faults before cutting.
A missed fault can become a rejected garment; an unsupported rejection can cause a disputed mill claim.
The product assists inspectors on existing inspection machines and links their decisions to evidence.
No numerical factory savings or defect reduction is claimed without a paired pilot.

## 3. Solution and architecture

Next.js (Bangla/English) → FastAPI → PostgreSQL. Video frames → sampling → interchangeable detector →
roll coordinates → deduplication → non-defect filter → inspector review → buyer-specific 4-point score.
Downstream: roll and lot verdicts, PDF evidence, claim packs, conservative cutting instructions,
supervisor approval and cutting-master acknowledgment, supplier scorecards and an audit hash chain.
Reference checks and benchmarks retain their inputs, tolerances, hashes and run history.

The edge deployment is Docker Compose with an internal network. The cloud demonstration uses Vercel
and Supabase. The local `make demo` profile uses CPU inference plus the shared Supabase database; it
therefore still requires internet. Docker is the separate offline product profile.

## 4. Links and access

- Repository: https://github.com/Shashwata2004/threadeye-ai — visibility/access to be verified by the owner.
- Hosted demonstration: https://threadeye-web.vercel.app — deployed version may precede this local work.
- Architecture and setup: [README](../../README.md).
- Judge access: [judge-access-note.md](judge-access-note.md).
- Measured evidence: [impact report](../impact/REPORT.md), [raw evidence](../impact/evidence.json).

## 5. Data and AI provenance

All demonstration video is simulated. Cloud detections can be answer-key-based simulation; local YOLOX-S
inference is real AI. Reports retain the source/provider distinction. The current model has 44 training epochs.
The line-scan regression roll's fabric group is excluded from training; repeated development use means it
is not a fresh blind evaluation. The model currently finds four of seven known faults with no false alarms
on that roll; it misses one crease and two broken yarns. Factory impact is not yet measured.

See [ml/DATASETS.md](../../ml/DATASETS.md) for source-level licences, mirrors, grouping and exclusions.
AITEX redistribution terms and other unresolved original-source terms must be confirmed before public
redistribution. This draft does not assert that all third-party material is commercially cleared.
Code currently carries the [MIT licence](../../LICENSE); older plan text saying otherwise is superseded by
that repository file. Model framework: YOLOX, exported to ONNX. Human-reviewed label exports are unassigned
for training and must be reviewed/grouped/split before reuse; no automatic retraining runs in the product.

## 6. Tooling, IDE and context

Python 3.12, uv, FastAPI/SQLAlchemy/Alembic; Next.js, TypeScript, pnpm; PostgreSQL; ONNX Runtime CPU;
ffmpeg; Docker Compose; pytest, Ruff, mypy, Playwright. Kaggle training scripts and the recorded compute
notes are under ml/. Claude-assisted development is described in TOOLING.md. Subsequent Codex-assisted
implementation, tests and documentation must also be disclosed; keep model/provider names as recorded
by the actual tool rather than guessing a model version. Team IDE roster remains owner-supplied.

## 7. MCP usage

See TOOLING.md for earlier session disclosures. Current implementation work uses local execution and
file editing; no external AI API is called by the product, and no repository publication or release
publication has been performed in this scope.

## 8. Prompts and limits

Earlier prompts are in PROMPTS.md. The continuation request is recorded in the milestone work record.
Known limits: trained detector misses long faults; verification is a reference-video software check,
not physical camera certification; cutting is a conservative whole-width plan, not garment nesting;
paired human/business impact data is still required. See docs/impact/PILOT_PROTOCOL.md.
