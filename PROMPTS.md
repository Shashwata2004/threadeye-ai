# Prompt Library

Every prompt that shaped this repository, recorded for the **Prompt Library** section of the
Idea to Unicorn submission. Entries are append-only. Each records: date, tool + model, who prompted,
the prompt (verbatim), attachments, and what it produced.

| # | Date | Tool / model | Purpose | Output |
|---|---|---|---|---|
| 001 | 2026-10-03 | Claude Code (desktop app, Code tab) · Claude Opus 5.5 (`claude-opus-5-5`) · plan mode | Full build plan from the team brief + two planning PDFs | `docs/PLAN.md` |
| 001a | 2026-10-03 | same session | Clarifying questions asked by the assistant, answered by the team | decisions recorded in `docs/PLAN.md` §2 |
| 002 | 2026-10-03 | same session | Plan updates (simulator conventions, training track, core-flow rule) + "implement M0 only" | updated `docs/PLAN.md`; M0 scaffold |

---

## #001: Build-plan brief (verbatim)

**Attachments:** `ThreadEye_AI_Workflow_Bangla.pdf` (22 pages), `ThreadEye_AI_Problem_Solution_Planning_Bangla.pdf` (12 pages). These are the team's own planning documents and are not committed here.

```text
You are in PLAN MODE. Do not write application code yet. This folder is empty and will become the project repository. Read this whole brief and the two attached PDFs, then produce a complete, reviewable build plan as described in Section 14. Ask me a few decisive questions before finalising; where something is not truly ambiguous, choose a sensible default and state it.

ATTACHED NOW
- ThreadEye_AI_Workflow_Bangla.pdf: our 22-page planning document (in Bangla): problem, app flow, 39 features with priorities, competitor differences, simulation, judging fit, ethics, timeline, risks, demo script.
- ThreadEye_AI_Problem_Solution_Planning_Bangla.pdf: our earlier "software lab" plan (FastAPI + Next.js + PostgreSQL + Docker Compose, AI provider abstraction, mock mode). Reuse its good engineering ideas; its scope is superseded by this brief.

NOT ATTACHED YET (will be copied into the repo later; plan for them now)
- Our roll simulator (Python): make_roll_video.py, sample_frames.py, evaluate.py, README. Planned location: tools/simulator/
- One simulated sample roll: roll_video.mp4, frames.csv, ground_truth.csv, nuisance.csv, roll_meta.json, roll_preview.png. Planned location: data/sample_roll/
Their exact formats are in Section 8. Design against those contracts.

==================================================
1. THE COMPETITION
==================================================
Event: International AI Builders Congress 2026, organised by CloudCamp Bangladesh, co-organised by Daffodil International University (cloudcampbd.com/ai-builders-congress).
- A six-month builder journey (1 July - 26 December 2026) ending in Congress Day: 26 December 2026, Daffodil International University, Ashulia Campus, Dhaka (5,000+ builders expected).
- Two competitions inside the Congress. We are in IDEA TO UNICORN (team-based; build a production-ready AI product). The other one, Zero to Launch, is an individual one-prompt challenge and is not our concern.
- Idea to Unicorn Preliminary Submission window: 1 July - 31 October 2026 (live event page, checked 1 Oct 2026).
- Final Submission: 24 December 2026 according to the FAQ. The FAQ has conflicting dates, so treat this as "to be confirmed on the dashboard".
- Congress Day judging: about 1 minute transition + 3 minutes pitch + 1 minute scoring per team, in front of a panel. There is also a pre-judging round that morning.
- Team size 3-6 (one FAQ answer says 3-5). Teams lock at some point; member changes after that need organiser approval.
- No participation fee. English for submissions and judging.

Submission requirements (official FAQ):
- Preliminary (mandatory): project name, one-line pitch, domain, challenge, structured problem statement, proposed solution, target user, prototype link or repo, team roles, initial mentor engagement notes. Video optional at this stage.
- Final adds: working demo link, GitHub repository, public/unlisted YouTube demo (3-5 minutes recommended, only first 7 reviewed) showing the product actually running with real inputs and outputs, tooling & IDE disclosure (including memory/context files such as CLAUDE.md), MCP usage disclosure, prompt library, Data & AI provenance.
- Eight submission sections: Basics, Problem Statement, Solution, Demo & Links, Data & AI Provenance, Tooling + IDE + memory/context files disclosure, MCP usage disclosure, Prompt Library.
- Links are validated PASS / RESTRICTED / FAIL; private links need a Judge Access Note.
- AI-assisted coding is allowed and expected but must be disclosed. Honest disclosure does not hurt scoring.
- Grounds for disqualification include faked demos, broken or fake demo links, plagiarism and misrepresentation. This matters for how we label simulated data (Section 11).
- Teams keep full IP of what they build.

==================================================
2. JUDGING CRITERIA (official, 100 points, at least 5 judges per submission)
==================================================
INNOVATION (20): originality, creativity, non-obvious AI application; meaningfully differentiated; AI applied in a transformative way; bold or systems-level thinking rather than incremental improvement.
  0-5 incremental or common idea | 6-10 moderately differentiated | 11-15 strong originality and creative AI integration | 16-20 breakthrough or globally competitive.
TECHNICAL EXECUTION (20): architecture quality, AI integration depth, system robustness; clarity of the input -> processing -> output workflow, model selection logic, integration of AI technologies (LLMs, ML, RAG, multimodal), code/workflow reliability, explainability of the intelligence core.
  0-5 basic prototype with limited AI | 6-10 functional, moderate depth | 11-15 well-structured AI-native system | 16-20 production-grade, ready for real deployment.
BUSINESS MODEL + GLOBAL READINESS (20): value proposition, monetisation or sustainability, adoption strategy, cross-border viability, evidence of market validation or demand.
  0-5 no model | 6-10 basic logic, limited validation | 11-15 viable pathway with defined users | 16-20 scalable, globally adaptable.
REAL-WORLD IMPACT + ETHICAL AI COMPLIANCE (20): significance of the problem, measurable outcomes/KPIs, societal or economic relevance, responsible data use, bias mitigation, transparency in AI design.
  0-5 weak or unclear | 6-10 clear local benefit | 11-15 strong national relevance with measurable outcomes | 16-20 high social return with DOCUMENTED ethical safeguards.
SCALABILITY + NRB COLLABORATION (10): technical and operational scaling, cloud readiness, modular architecture, infrastructure feasibility, collaboration with Non-Resident Bangladeshis / global builders, international standards.
  0-3 demo-only | 4-7 early strategy | 8-10 clear deployment pathway and strong global collaboration.
PRESENTATION (10): storytelling, demo effectiveness, ability to explain AI decisions, professionalism.
  0-3 unclear | 4-7 clear | 8-10 compelling, data-driven, investor-ready.

Scoring mechanics: each judge's total normalised to 0-100; trimmed mean with 4+ judges; a gap of 25+ points triggers an extra judge; ties broken by Innovation, then Technical Execution, then Real-World Impact, then earlier submission. FAQ bands: 0-39 Emerging, 40-59 Promising, 60-74 Strong, 75-89 Excellent, 90-100 World-Class; named awards usually need Strong or above.

What this means for the build: ordinary software (forms, dashboards, CRUD) is not where marks come from. Marks come from (a) a clean, explainable, swappable AI pipeline with a measurement/benchmark story, (b) the systems-level chain defect -> decision -> money -> cutting -> supplier, (c) measurable KPIs, (d) documented ethics and safeguards, (e) an edge/offline-capable architecture.

==================================================
3. OUR DOMAIN AND CHALLENGE
==================================================
Domain: INDUSTRYSPHERE AI - "Intelligent, resilient, sustainable industrial operations and supply chains." Its five challenges: Factory Brain (AI operations layer for the connected factory), Predictive Plant (predictive maintenance), QUALITY VISION (automated visual quality inspection), Supply Chain Nexus (end-to-end supply-chain optimisation and resilience), Green Manufacturing (energy and emissions optimisation on the line).

Our challenge: QUALITY VISION - Automated visual quality inspection.
- Specific ask: defect reduction and yield.
- Details: vision models + edge deployment.
- Example directions from the organisers: few-shot learning to identify defects from very few labelled images; a Vision Transformer for anomaly detection under variable lighting; GAN-based synthetic data for rare defects; federated learning so several plants train together without sharing images; an Explainable AI dashboard that highlights the pixels behind a "fail" decision to help technicians with root-cause analysis.
- Suggested data sources: NEU Surface Defect Database, MVTec AD, UCI SECOM, NASA Prognostics, Azure Open Datasets (factory IoT).
- Reference companies: Cognex, Instrumental, Landing AI, Sight Machine, Nanotronics.
We also touch Supply Chain Nexus (supplier quality, claims) and Green Manufacturing (less fabric waste) for the systems-level story, but our registered challenge is Quality Vision.

==================================================
4. THE INDUSTRY PROBLEM (Bangladesh garment fabric inspection)
==================================================
- Ready-made garments are roughly 80% of Bangladesh's exports (BGMEA, FY 2025-26). About 78% of Bangladesh's fabric imports came from China in 2024; woven fabric is heavily imported, knit fabric is mostly local.
- Flow: buyer order -> fabric rolls arrive from mills -> FABRIC INSPECTION in the factory's fabric store -> cutting -> sewing -> finishing -> final inspection -> shipment.
- Today fabric is inspected on a fabric inspection machine: the roll unwinds over an inclined, lit (often back-lit) board and is rewound on the other side; a meter/yard counter shows position. An inspector watches, stops the machine at a defect, measures it, puts a coloured sticker on the selvage next to it, and writes it on paper or Excel. Scoring uses the 4-point system. Many factories inspect only a sample of rolls (often said to be about 10%, buyer-dependent).
- Pain points: slow and tiring; inconsistent between inspectors; small defects missed; not all rolls inspected; paper records with no photo evidence; weak claims against mills (often foreign); defect locations never reach the cutting room, so bad fabric gets cut and sewn; no supplier quality history.
- Competitors / prior art (details limited, be careful): ThreadBridge (Bangladesh; AI smart glasses + mobile app detecting fabric and sewing defects in real time; reported in 4 garment factories, May 2026); Smartex (Portugal; cameras on knitting machines at mills; about $24.7M raised in 2022); Uster Fabriq Vision (Switzerland; automated fabric inspection systems for fabric producers).
- Our positioning: a retrofit camera on EXISTING inspection machines at the garment factory's receiving inspection, turning every defect into a decision: roll verdict, claim evidence, cutting instructions, supplier score.

==================================================
5. DOMAIN RULES THE SOFTWARE MUST IMPLEMENT EXACTLY
==================================================
4-point system (every number configurable per buyer rule profile):
- Defect length (largest dimension) <= 3 in -> 1 point; 3-6 in -> 2; 6-9 in -> 3; > 9 in -> 4.
- Holes/openings: <= 1 in -> 2 points; > 1 in -> 4 points.
- Maximum 4 points per linear yard (sum per yard, capped).
- Continuous (running) defects spanning several yards: 4 points for every yard they span.
- Selvage exclusion: many buyers ignore defects within 1 inch of the selvage; per-buyer toggle and distance.
- Points per 100 sq yd = total points x 3600 / (yards inspected x fabric width in inches).
- Roll verdict: PASS if <= buyer threshold (default 40); FAIL if above; BORDERLINE if within a configurable band around the threshold (supervisor decides).
- Lot (delivery) verdict: configurable rule, e.g. "if more than X% of inspected rolls fail, hold the lot / inspect 100%".
- Length/width check: measured length (from the counter) and width (from the fabric edges) vs the mill's declared values; flag shortage.
- Naming: never claim formal standard compliance (ASTM/AQL) unless implemented exactly; call it a "4-point inspection report".

Things on real fabric that are NOT defects (our simulator includes them on purpose): inspector stickers on the selvage, loose threads lying on the fabric, handling wrinkles, stenter pin holes along the selvage, the board visible beside the fabric, the inspector's hand. False alarms on these are the biggest real-world failure; the app must track and report them.

==================================================
6. USERS AND THE ROLL JOURNEY (the app workflow)
==================================================
Roles: Inspector, QC Supervisor, Store In-charge, Cutting Master, Merchandiser/Sourcing, Management, Admin.
1. Roll registration (Store): delivery/challan, mill, buyer, fabric type/colour, declared length and width; print a QR roll label; show a sampling suggestion from the mill's history.
2. Load roll (Inspector): scan QR; the buyer rule profile is applied automatically.
3. Live inspection (camera + detector): frames -> detector -> defects drawn as boxes; live yard counter, speed, running/stopped state, running points and points per 100 sq yd vs threshold; non-defects shown differently and not scored.
4. Inspector confirmation: confirm / reject / change class per defect in one click (voice later); stops are logged.
5. Roll verdict: totals, breakdown by defect type, verdict, length/width check, count of ignored non-defects.
6. Report and roll map: the whole roll as one strip with defect markers; PDF report with photos; a short video clip per defect as evidence.
7. Claim pack: one-click claim letter (English first) with photos, positions, points, rule, shortage.
8. Cutting instructions: yard ranges to skip or splice; usable length.
9. Supplier scorecard and learning: results roll up per mill; inspector corrections are stored as labelled data for future model training.

==================================================
7. SCOPE NOW: NO EXTERNAL AI API, NO MODEL TRAINING
==================================================
We are not calling any AI API and not training any model in this phase. Design the AI layer so both can be added later without touching the rest of the app:
- FrameSource interface: VideoFileSource (simulator video + frames.csv) and WebcamSource (later, for our PVC-pipe test rig), same contract for both.
- DetectorProvider interface returning, per frame: a list of {bbox (frame pixels), class, confidence or null, explanation text}.
  * SimulatedDetector (build now): reads the simulator's ground_truth.csv and nuisance.csv, maps them into the current frame using frames.csv, and behaves like an imperfect detector with configurable miss rate, localisation jitter, class confusion, and a configurable chance of falsely flagging non-defects. Seeded and deterministic. This lets us build and test the whole pipeline, the false-alarm filter, and the evaluation page.
  * ApiDetector and LocalModelDetector: interfaces/stubs only, with a clear TODO and a config switch. Do not implement calls or training.
- The UI and every report must show which provider produced the detections, and show "SIMULATED DETECTIONS" whenever SimulatedDetector is active. Never present simulated detections as real AI output.
- Optional stretch, only if time allows and clearly labelled as a classical baseline (not AI): a simple OpenCV texture-anomaly detector.

==================================================
8. DATA CONTRACTS FROM THE SIMULATOR (files arrive later)
==================================================
roll_meta.json: px_per_cm, view_region {x,y,w,h} (camera view without the info bar), fabric_width_cm, fabric_width_in, roll_length_yd, fps, frames, expected_score {total_points, points_per_100_sq_yd, threshold, verdict}, selvage_band_px, mode (realistic or clean).
frames.csv columns: frame, time_s, roll_y_top_px, top_yd, bottom_yd, speed_m_min, state (running/stopped), fabric_x0_px, hand_visible. Speed is not constant (the operator stops at defects) and the fabric drifts sideways.
Pixel -> roll position: roll_y_px = roll_y_top_px[frame] + y ; yard = roll_y_px / px_per_cm / 91.44 ; across_cm = (x - fabric_x0_px[frame]) / px_per_cm.
ground_truth.csv columns: defect_id, class, center_yd, start_yd, end_yd, across_cm, length_in, points, first_full_frame, last_full_frame, operator_stop_frame, x0_px, y0_px, x1_px, y1_px (roll coordinates), source.
nuisance.csv columns: type (wrinkle / loose_thread / sticker), center_yd, across_cm, extent_cm, appears_frame.
Video: 1920 px wide, about 1044 px tall; fabric enters at the bottom and exits at the top; a "SIMULATED FEED" info bar at the bottom (crop it using view_region). The sample roll is about 13 yards, 1,729 frames at 30 fps, 8 defects, 17 non-defect distractions, expected 10 points = 46.4 per 100 sq yd -> FAIL.

Pipeline rules to reuse:
- Frame sampling by fabric travel, not by frame count: take a frame each time the fabric has moved view_length x (1 - overlap), default 15% overlap; take none while stopped; avoid frames with the hand in view when a nearby clean one exists.
- De-duplication: convert detections to roll coordinates and merge sightings of the same defect (IoU > 0.3 or centres within about 3 cm), averaging the box.
- Evaluation: implement the same metrics as our evaluate.py (precision, recall, F1, recall per class, class accuracy, predicted vs true 4-point score, false positives explained by non-defect type) and show them on a Benchmark page. Keep a train/test split concept in the data model for later (never evaluate on data used for training).

==================================================
9. FEATURE PRIORITIES
==================================================
Use the feature list in ThreadEye_AI_Workflow_Bangla.pdf (39 features tagged competition / next / future) as the master list, with these changes.

MUST WORK FULLY BY THE FINAL SUBMISSION:
roll registration + QR label; live inspection screen with yard tape, speed/state and live points meter; detector provider switch (Simulated now); de-duplication; false-alarm filter (non-defects shown, not scored, counted); one-click confirm/reject/reclass; 4-point engine with buyer rule profiles INCLUDING continuous-defect and selvage-exclusion rules; roll verdict incl. BORDERLINE; LOT VERDICT; photo report (PDF); roll map; DEFECT VIDEO CLIPS; claim pack (English); cutting instructions + usable length; supplier scorecard; dashboard; audit log; role-based access; POWER-LOSS SAFETY (every event persisted immediately; resume a roll at the same yard); DAILY VERIFICATION RUN (run a known reference roll, compare with its answer key, show green/red); benchmark page; demo/simulation mode with visible labels; Bangla + English UI.

NEXT (design for, build later): API detector, local model detector, Bangla voice commands, camera-health alerts, offline sync, width measurement from fabric edges, smart sampling, shade/colour grouping with a reference colour card, bow/skew detection, buyer read-only report link, meter-counter OCR, training mode for new inspectors, "ask a question" chat, weekly summary, money-saved dashboard, Chinese claim letter.

FUTURE: roll-to-lay planning, roll -> bundle -> garment traceability, industry-wide anonymous mill rating, ERP export.

==================================================
10. ARCHITECTURE PREFERENCES (change them only with a stated reason)
==================================================
- Backend: Python FastAPI; PostgreSQL; a background worker for video/frame processing; file storage for frames, clips and reports.
- Frontend: Next.js + TypeScript (or a simpler stack if you can justify it for a 4-person student team); Bangla font (Hind Siliguri or Noto Sans Bengali); i18n bn/en.
- Realtime: SSE or WebSocket for the live screen.
- Deployment: Docker Compose; must run on one laptop WITHOUT internet (edge-first story); no cloud dependency in the core path.
- Append-only inspection events so a power cut never loses data; idempotent resume.
- Security baseline: hashed passwords, server-side role checks, validated uploads, parameterised queries, secrets only in environment variables, CORS locked down, append-only audit log.
- Tests: unit tests for the 4-point engine (all rules incl. continuous and selvage), coordinate mapping, de-duplication, lot verdict; an integration test that runs the sample roll end-to-end and asserts the expected score from roll_meta.json when SimulatedDetector has 0% misses and 0% false alarms; a resume-after-crash test.

==================================================
11. HONESTY AND LABELLING RULES (non-negotiable)
==================================================
- Everything simulated is labelled as simulated in the UI, reports, exports, and any demo video we record.
- No fabricated metrics anywhere. Sample/fictional data (mill names, dashboard numbers) must be marked "sample data".
- The final YouTube demo will need real inference (API or our own model); keep that path open and do not design anything that only works with ground truth.
- Create PROVENANCE.md and TOOLING.md from day one (datasets and licences, AI tools, IDEs, memory files, MCP servers used, and a prompt library). Record this very prompt in the prompt library.

==================================================
12. TEAM AND TIMELINE
==================================================
- Team of 4 today (possibly +1 textile domain member, +1 business member). Roles from our earlier plan: A Backend, B Frontend, C AI/Integration (provider interfaces, simulator integration, evaluation), D Reports/QA/Demo.
- Today is early October 2026.
  * By 31 October (preliminary): repo public or with judge access; core flow working on the sample roll with SimulatedDetector: registration -> live inspection -> 4-point verdict -> roll map -> basic PDF report; README with an architecture diagram.
  * November: the rest of the must-have set; benchmark page; daily verification; power-loss resume; claim pack; cutting; supplier scorecard. (API and our own model are plugged in later, outside this plan.)
  * 1-24 December: polish, Bangla UI pass, demo video with real inference, submission documents.
- Plan milestones that each end in something runnable and demoable. Assign tasks to A/B/C/D so they can work in parallel, with API contracts agreed first.

==================================================
13. NON-GOALS FOR THIS PHASE
==================================================
No external AI API calls. No model training or fine-tuning. No hardware integration beyond reading video files (the webcam source can be a stub). No multi-factory tenancy. No payment or billing.

==================================================
14. WHAT YOUR PLAN MUST CONTAIN
==================================================
1. A one-paragraph restatement of the product and the competition goal.
2. Assumptions and open questions (few and decisive).
3. System architecture diagram (text or mermaid) with a short rationale for each major choice, tied to the judging criteria where relevant.
4. Data model: entities, key fields, relations, including events/audit, buyer rule profiles, lots, rolls, inspections, frames, detections, confirmations, de-duplicated defects, clips, reports, claims, suppliers, verification runs, evaluation runs, provider config.
5. Backend API endpoints and the realtime channel contract.
6. The detection pipeline step by step (frame source -> sampling -> provider -> mapping to roll coordinates -> de-duplication -> non-defect filter -> confirmation -> scoring), with the exact FrameSource and DetectorProvider interfaces.
7. The 4-point and verdict engine spec with worked examples and edge cases.
8. Screen list: purpose and main components of each screen, and the Bangla/English text approach.
9. Repository folder structure for this empty folder, including where tools/simulator/ and data/sample_roll/ will go.
10. Milestones with deliverables, owner (A/B/C/D), dependencies and acceptance criteria; mark the preliminary-submission milestone clearly.
11. Test plan (unit, integration, resume-after-power-loss, verification run).
12. Risks and mitigations.
13. What must be added later for ApiDetector and LocalModelDetector so they slot in without refactoring.

Write the plan in English. Suggest user-facing UI text in Bangla.
```

**Output:** `docs/PLAN.md` (v1).

## #001a: Clarifying questions (assistant → team) and answers

| Question | Answer chosen by the team |
|---|---|
| Frontend stack (Vite SPA vs Next.js) | Next.js + TypeScript |
| Repo sharing / licence | Public, all rights reserved |
| Where the final demo link runs | "Free hosting only: Vercel Hobby (frontend + FastAPI as two projects) and Supabase free tier. Add a GET /health endpoint that runs a trivial DB query, and a GitHub Actions scheduled workflow that calls it once a day so the Supabase free project never pauses during judging (Nov-Dec)." |
| Keep the name "ThreadEye AI"? | Keep ThreadEye AI |

## #002: Plan updates + implement M0 (verbatim)

```text
Before scaffolding further, apply these updates to docs/PLAN.md, then implement only M0.

A. Answers to Q1 (verified in tools/simulator/make_roll_video.py):
- y in roll_y_px = roll_y_top_px + y is measured from the top of view_region (view_region is x=0, y=0, w=1920, h=1008; a 36 px label bar sits below it).
- ground_truth.csv x0_px..y1_px are ROLL coordinates, not frame coordinates: x is relative to the fabric's left edge, y is absolute along the roll (roll px). The overlay draws them as (x0_px + fabric_x0_px[f], y0_px - roll_y_top_px[f]).
- GT boxes are already clipped to exclude the selvage band (selvage_band_px); defects fully inside the selvage are not in the answer key.
- length_in = max(width_cm, height_cm) / 2.54 of the clipped box.
- expected_score rules ("simulator-parity" profile): length bands and hole bands only, cell = floor(center_yd), cap 4 per cell, NO continuous rule, NO selvage exclusion, NO borderline band, per-100 = total * 3600 / (roll_length_yd * fabric_width_in) using roll_meta values, PASS if per-100 <= threshold. Exact value for the sample roll: 10 points, 46.45, FAIL.

B. Add a model-training track (owner C, starts M4, 1 Nov). The final product uses our own trained model; December alone is too late.
- M4: simulator export of YOLO-format training frames with train/val/test split BY SOURCE IMAGE (no leakage), including nuisance frames as hard negatives.
- M5: train a baseline YOLO detector, export to ONNX, model card.
- M6: LocalModelDetector working on the edge laptop (CPU, ONNX Runtime) and benchmarked on split=test against the simulated baseline.
- M7: improve the model and integrate; the cloud demo keeps SimulatedDetector with clear labels.

C. Rule for every milestone: the core flow (load roll → live inspection → confirm → verdict → report) must work end to end before any extra feature in that milestone starts.

D. Now implement milestone M0 only. When done, run the M0 acceptance criteria yourself, fix failures, then stop and report: what was built, which acceptance criteria pass, what needs a human (accounts, files, decisions), and the exact commands for me to verify it. Do not start M1.
```

**Output:** `docs/PLAN.md` (v2) and the M0 scaffold (see the git history).

---

## Template for new entries

```text
## #NNN: <short purpose>
- Date: YYYY-MM-DD
- Tool / model: <e.g. Claude Code desktop · claude-opus-5-5>
- Prompted by: <team member role>
- Attachments: <files>
- Prompt (verbatim): <text>
- Output: <files/commits/PRs>
```
