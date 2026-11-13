# CloudCamp Judge Demonstration

Use this order so judges see the original product first and the optional evidence companion second. Never present the
companion as the inspection product or a simulated detector as trained inference.

## System A — original ThreadEye fabric-inspection platform

### Demonstration boundary

ThreadEye covers receiving → roll registration → QR traceability → inspection → inspector correction → deterministic
four-point scoring → supervisor decision → bilingual report/evidence. Trained YOLOX-S ONNX CPU inference is a local
capability. The hosted cloud demonstration deliberately uses a simulated detector and must be labeled that way.

### Option 1: hosted simulated workflow

- Web: `https://threadeye-web.vercel.app`
- API health: `https://threadeye-api.vercel.app/health`
- Prompt 12 check: both returned HTTP 200 on 2026-11-13.
- Limitation: HTTP availability, deployed revision, login and the full authenticated flow were not verified in this
  audit. The detector is simulated.

### Option 2: local trained-model workflow

From the repository root, prepare the team-controlled `.env.cloud` without displaying secrets, then run:

```bash
make cloud-migrate
make demo
```

Open the URL printed by the command (normally `http://localhost:3000`; the launcher may choose another free API
port). Show, in order:

1. Log in with a role authorized for the intended operation.
2. Receive and register a fictional roll; point out the supplier/lot metadata.
3. Generate or inspect the roll QR and trace it into inspection.
4. Run the local roll video through the trained model; show the UI's real/simulated mode indicator.
5. Correct one proposed defect and record a reason to demonstrate human control.
6. Show the deterministic four-point result separately from model detections.
7. Change to the supervisor role and record a decision.
8. Open the Bangla and English report/evidence views.

Prompt 12 did not rerun this real-model path or connect to Supabase. Perform a supervised rehearsal before recording.
Press Ctrl-C in the launcher terminal for clean shutdown.

### System A evidence and limitations

- Product architecture and commands: repository `README.md`.
- Model provenance and simulated-cloud disclosure: repository `PROVENANCE.md`.
- Tool provenance: repository `TOOLING.md` and `PROMPTS.md`.
- Do not claim hosted YOLOX, production deployment validation, factory ROI, autonomous verdicts or Prompt 12 model
  execution.

## System B — isolated ThreadEye Evidence Assistant

### One-time local preparation

From `threadeye-evidence-assistant/`:

```bash
cp .env.db.example .env.db
# Set unique local-only values in .env.db; never record or share them.
docker compose --env-file .env.db up -d --wait
set -a; source .env.db; set +a
export THREADEYE_EVIDENCE_DATABASE_URL="postgresql://${EVIDENCE_DB_USER}:${EVIDENCE_DB_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
export THREADEYE_EVIDENCE_ADMIN_DATABASE_URL="postgresql://${EVIDENCE_DB_ADMIN_USER}:${EVIDENCE_DB_ADMIN_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
export THREADEYE_EVIDENCE_MCP_DATABASE_URL="postgresql://${EVIDENCE_MCP_DB_USER}:${EVIDENCE_MCP_DB_PASSWORD}@127.0.0.1:${EVIDENCE_DB_PORT}/${EVIDENCE_DB_NAME}"
export THREADEYE_EVIDENCE_MCP_CONFIG="$PWD/config/mcp-synthetic.json"
export THREADEYE_EVIDENCE_MODEL_CACHE="$PWD/build/model-cache"
PYTHONPATH=src .venv/bin/python -m threadeye_evidence index
PYTHONPATH=src .venv/bin/python -m threadeye_evidence.mcp.database
```

The connection strings are process-local examples; never paste expanded values into evidence or video. The database
is isolated from ThreadEye/Supabase and the MCP identity is SELECT-only.

### Launch

```bash
read -s THREADEYE_EVIDENCE_UI_ACCESS_CODE
export THREADEYE_EVIDENCE_UI_ACCESS_CODE
export THREADEYE_EVIDENCE_UI_PORT=8770
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src \
  .venv/bin/python -m threadeye_evidence.ui.launcher
```

Open `http://127.0.0.1:8770` (not `localhost`) and enter the same operator-controlled code.

### Verified judge sequence

1. Confirm `MCP connected` and explain that the official MCP client calls one custom read-only server.
2. Search `content hash sanitized observation` in hybrid mode. Inspect branch ranks and citations; RRF is a ranking
   score, not confidence.
3. Ask `Which supplier lot is recorded for ROLL-NST-204?`. Inspect the exact cited fictional passage and normalized
   source span.
4. Ask `What is tomorrow's weather in Dhaka?`. Show `ABSTAINED`, no answer and zero citations.
5. Explain the real path: fictional approved evidence → BGE embedding → PostgreSQL FTS/pgvector → weighted RRF →
   deterministic extraction → citation validation → browser.

Current Chrome evidence covers desktop and mobile layouts, search, supported answer, citation inspection, abstention,
unauthorized denial, CSRF/body-size defenses, logout and clean child-process shutdown. Exact returned text can change
when approved fixtures change; verify live rather than memorizing an output.

### Troubleshooting and shutdown

- Port busy: stop the existing local process or choose distinct loopback UI/MCP ports.
- Startup fails safely: verify the three database URLs, fixed MCP config/model cache and access code are present.
- MCP unavailable: do not present the UI as connected; check database health and sanitized local logs.
- Login rejected: use the exact `127.0.0.1` origin and the operator-provided code.
- Stop: press Ctrl-C, confirm the owned MCP subprocess exits, then run
  `docker compose --env-file .env.db down`.

System B is a localhost synthetic-evidence demonstration, not production identity/TLS/OAuth, a public service, a
generative LLM, a factory inspection system or evidence of business impact.
