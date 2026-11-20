# ThreadEye project guidance

## Project and scope

ThreadEye assists fabric-roll inspection: receive a challan and its rolls, inspect
video, review defects, record a supervisor decision, and issue cutting directions
and claim evidence. A challan contains rolls; roll verdicts and the final challan
decision are separate records.

- `backend/threadeye/`: FastAPI API, domain logic, persistence and inference.
- `backend/tests/`: backend unit and integration tests.
- `frontend/`: Next.js app with Bangla and English messages.
- `data/`: bundled demo videos, metadata and stable model assets.
- `ml/` and `scripts/`: model training, evaluation and operational tools.
- `threadeye-evidence-assistant/`: evidence retrieval and grounded answers.
- `docs/`: architecture, API contract, milestones and measured results.
- `specs/`: proposed features; status and unchecked tasks indicate pending work.

Read more specific guidance in the directory being edited. In particular,
`frontend/AGENTS.md` points to the bundled Next.js documentation for this version.
Do not replace its generated rules with assumptions from older Next.js versions.

## Product invariants

- Distinguish simulated camera footage from simulated detections. A real model
  can run on simulated footage. Display the actual provider recorded for the
  inspection; do not infer it from the video being a demo.
- Preserve historical inspection provider snapshots, model identities, rules,
  supervisor decisions and cutting acknowledgements. Switching the default
  model must not rewrite previous inspections.
- Keep roll QC verdict, supervisor acceptance, lot/challan decision, cutting
  approval, and cutting acknowledgement distinct. An acknowledgement identifies
  who received the directions; it does not grant QC decision permission.
- Enforce permissions at the backend. A denied request must appear as a clear
  permission message in the UI, not an apparently empty dataset.
- Keep Bangla and English messages aligned. Avoid hard-coded locale keys and
  nested paragraph elements in reusable notice components.
- Roll position is measured in yards; defect size may be in inches. Label units
  explicitly and preserve existing four-point scoring and buyer cutting rules.
- A detector's class score is not calibrated probability. Human confirmation
  does not prove the detector was correct on unseen data.

## Model and data integrity

The visual detector, embedding encoder, and generative LLMs are different systems.
Do not describe YOLOX or BGE embeddings as a generative local LLM. Check the actual
runtime path before documenting a model or tool as integrated.

Inspector corrections are review data, not automatic online training. Exported
labels require provenance checks, deduplication, human label review and a source
split before training. Preserve rejected flags as review decisions rather than
turning them into positive defect labels. Model confirmation of an answer-key
detection does not make the original label an independent human annotation.

Group train/validation/test data by original donor and background, not by rendered
frame or augmented image. Never tune thresholds on a final test set. Report
localization and class accuracy separately, including missed broken yarn, false
alerts and production CPU processing time. A better overall average alone is
insufficient evidence for replacing the line-scan model.

The stable ONNX file and the five team demo videos are intentionally tracked;
see `data/demo-assets.json` and the explicit `.gitignore` exceptions. Keep
temporary training outputs and generated presentation media outside tracked
source. Do not add presentation recording or voiceover tooling to the app.

## Implementation and commands

Preserve both the edge/offline deployment and Vercel/cloud execution paths.
Cloud functions have different time, memory and response-size limits. Avoid
assuming long-lived background jobs, process-local caches or local storage are
durable on Vercel.

Use the existing architecture and dependency lockfiles. Keep API contract changes
in sync with `docs/api/openapi.json` and the generated frontend schema using
`make openapi`; do not hand-edit generated types.

Relevant commands from the repository Makefile:

| Command | Purpose |
| --- | --- |
| `make demo` | Run the local demo launcher |
| `make test-backend` | Backend tests using the disposable test database |
| `make test-frontend` | Locale parity, lint and TypeScript checks |
| `make lint` | Backend and frontend static checks |
| `make openapi` | Regenerate API JSON and frontend types |
| `make assets-check` | Check bundled model/video hashes |
| `make impact` | Generate measured local-model impact results |

Choose checks appropriate to the change and the user's scope. Report commands
actually run and relevant failures; do not mark unchecked acceptance criteria
as passed. Test against the disposable database, never a shared cloud database.

## Credentials, evidence and workflow

Never commit `.env` files, credentials, tokens, private exports or production
connection strings. Avoid printing secrets while diagnosing configuration.
Respect existing user authorization for publishing and deployments; ordinary
implementation does not itself request a new deployment.

Keep audit evidence append-only and preserve model/source hashes. Keep measured
results, estimates, proposed work and actual factory outcomes explicitly separate.
New framework files establish setup, not proof that the framework was used for
earlier development. Record material tooling changes in `TOOLING.md`.

For new specified work, read `.specify/memory/constitution.md` and the relevant
`specs/<feature>/spec.md`, `plan.md`, and `tasks.md`. Update task status only when
the corresponding work has actually been performed.
