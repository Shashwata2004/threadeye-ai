# Three-Minute CloudCamp Video Package

Current public CloudCamp submission rules checked on 2026-11-13 specify a **three-minute** concept/prototype video.
Keep the final file at or below 3:00 and use only real application/prototype footage.

## Narration and shot list

### 0:00–0:20 — problem and product

**Picture:** title over a real ThreadEye login/dashboard capture, then a fabric-roll receiving screen.

**Narration:** “Garment teams can discover fabric defects too late, after manual records have separated a roll from
its inspection evidence. ThreadEye connects receiving, defect review, quality decisions and supplier evidence in one
traceable workflow for inspectors, supervisors and downstream teams.”

### 0:20–1:35 — original product workflow

**Picture:** receiving → registration → QR → inspection → proposed detections → human correction → four-point result
→ supervisor decision → Bangla/English report.

**Narration:** “An operator registers a roll and supplier lot, then uses its QR identity throughout inspection. A
local deployment can run our trained YOLOX-S ONNX model on CPU to propose defect regions. The inspector remains in
control: they review or correct classifications and record a reason. ThreadEye then applies a transparent,
deterministic four-point calculation—separate from the detector—and routes the evidence to a supervisor. The approved
decision produces traceable reports in Bangla or English for cutting, merchandising and management.”

**On-screen disclosure:** `Local trained-model demo` if actually running local YOLOX; otherwise
`Hosted workflow demo — detector simulated`. Never mix these labels.

### 1:35–2:15 — architecture and responsible controls

**Picture:** simple architecture diagram plus audit/provenance and role-controlled views.

**Narration:** “The design separates model suggestions, deterministic scoring and human approval. Role-based access,
audit records, correction reasons and evidence exports support review rather than autonomous acceptance. Training and
model provenance are documented. Demonstration data and videos are disclosed, and factory impact remains a pilot
hypothesis—not a measured ROI claim.”

### 2:15–2:45 — Evidence Assistant

**Picture:** local companion UI, hybrid results, one opened citation and the weather abstention.

**Narration:** “Our isolated Evidence Assistant demonstrates accountable technical proof over fictional evidence. It
uses pinned BGE embeddings, PostgreSQL full-text and pgvector search, weighted reciprocal-rank fusion, and one
read-only MCP server. Answers are deterministic extracts with validated citations. When evidence is missing, it
abstains. This is not a generative LLM and it does not access production ThreadEye data.”

### 2:45–3:00 — differentiation, next step and limits

**Picture:** split view of ThreadEye workflow and cited evidence, followed by a team/contact end card.

**Narration:** “ThreadEye turns reviewed visual detections into auditable factory decisions, while keeping humans and
evidence in the loop. Our next step is a controlled mill pilot to validate detection, workflow and business KPIs.
Today, the hosted detector is simulated and the real trained model runs locally.”

## Recording checklist

- Rehearse the exact roles, fictional roll and expected navigation; remove notifications and unrelated windows.
- Record System A first. Show the mode banner and never use fabricated factory/production footage.
- Show at least one human correction, deterministic score, supervisor decision and bilingual report.
- Record System B locally with only fictional evidence; open one citation and one abstention.
- Avoid passwords, database URLs, access codes, tokens, private repo pages, real contracts and personal data.
- Keep labels readable at 1080p, cursor movement deliberate, audio clear and total duration no more than 3:00.
- Add captions and verify Bangla/English spelling. Avoid claims not in `CLAIM_MATRIX.md`.
- Final review by product, ML and team leads before upload.

## Required end-card disclosure

> Prototype/development demonstration. Hosted defect detection is simulated; trained YOLOX-S inference is local.
> Evidence Assistant uses fictional data and deterministic extractive answers, not a generative LLM. Factory impact
> and ROI have not yet been validated in a production pilot.

## Upload and proof checklist

- Upload to the team-approved YouTube account as Public or Unlisted, according to the form rule.
- Set an accurate title/description, list models/tools/data provenance and include access instructions if needed.
- Play the uploaded video from a signed-out/incognito browser; confirm audio, captions, resolution and duration.
- Confirm no copyright-restricted, confidential or misleading footage appears.
- Paste the canonical `https://www.youtube.com/watch?...` URL into the form and reload the saved response if the
  official form supports it.
- Record uploader, date and final accessibility result in `SUBMISSION_LINK_AUDIT.md`.

**Final YouTube URL:** `MISSING — recording and upload are human/external actions.`
