# CloudCamp Claim Matrix

Access date: 2026-11-13. `Official` below means supported by the public CloudCamp submission or AI-usage policies.
The detailed checkbox point schedule was not publicly accessible; no current point total is predicted.

## Pre-judgment claim audit

| Category / criterion | Source status | Evidence status | Implementation / test evidence | Remaining blocker | Suggested truthful wording | Confidence limit |
|---|---|---|---|---|---|---|
| Clear problem and target users | Official | Implemented and documented | Root `README.md`, `docs/congress/one-pager.md`, roles and workflow tests | Team must confirm final wording | “ThreadEye helps garment receiving/QC teams detect, review and trace fabric-roll defects before cutting.” | Product value is documented; factory adoption is not measured |
| AI-native approach | Official | Implemented locally | YOLOX-S ONNX provider, provider abstraction, model cards, historical real-model tests | Real local inference was not rerun in Prompt 12 | “The local product can run a trained YOLOX-S ONNX detector; inspectors correct predictions before deterministic scoring.” | Hosted demo uses a simulated detector |
| Basic system flow | Official | Implemented and historically browser-tested | Receiving → QR → inspection → correction → scoring → supervisor → evidence | Record a clean current product video | Use the exact flow shown in `JUDGE_DEMO.md` | Evidence Assistant is a separate companion |
| Initial demo/prototype/workflow | Official | Product URL responds; local workflow implemented | `https://threadeye-web.vercel.app` HTTP 200; root validation docs | Authenticated hosted flow and deployed SHA not verified | “A hosted simulated workflow is available; the trained detector is demonstrated locally.” | HTTP 200 is not functional-flow proof |
| Bangla/localization | Official | Implemented | bn/en UI and report evidence; historical frontend i18n parity | Show both languages in video | “The application and inspection report support Bangla and English.” | Prompt 12 did not rerun original frontend checks |
| Impact/KPIs | Official | Definitions and measured development evidence exist | `docs/KPIS.md`, `docs/impact/REPORT.md`, pilot protocol | No factory pilot or ROI validation | “Development fixtures measure detection and decision risks; factory KPIs require a pilot.” | Never claim measured factory savings |
| AI/data/tool provenance | Official | Documented | Root `PROVENANCE.md`, `TOOLING.md`, `PROMPTS.md`, companion reports | Team-member IDE table remains incomplete | Disclose Claude Code, Codex, Kaggle, datasets, simulated video and model limitations | External contribution review remains human-owned |
| Responsible data use | Official | Strong development boundary | Synthetic companion corpus, approval manifests, privacy/security tests | AITEX redistribution question remains open | “Companion evidence is fictional; real documents are not approved for ingestion.” | Not a production privacy certification |
| Team information | Historical field family | Incomplete externally | Repository roles are not an official roster | Team leader must verify names, roles, mentors/NRB contribution and consent | Enter only confirmed team facts | No automatic evidence of mentor engagement |
| Required preliminary video | Official | Missing external proof | Script is prepared | Record, upload public/unlisted, verify URL | “Three-minute prototype demonstration.” | Do not claim uploaded until verified |

Historical screenshot value: **251/425**. It is not recalculated because the official private point formula could not
be verified. Completing YouTube, Figma, repository access and team fields may improve completeness, but no point gain
is claimed.

## Submission claim audit

| Historical section / criterion | Evidence status | Implementation / proof | Remaining blocker | Suggested truthful wording | Do not claim |
|---|---|---|---|---|---|
| Story / problem / solution | Supported | Root one-pager, README, implemented workflow | Final team-approved concise text | “Retrofit existing inspection machines and turn reviewed defects into decisions, reports, cutting guidance and supplier evidence.” | Market adoption or revenue without evidence |
| Proof / demo links | Partially supported | Web/API HTTP 200; local browser evidence | YouTube missing, Figma missing, GitHub unauthenticated 404, deployed SHA unknown | List access requirements and separate hosted-simulated vs local-real detector | Broken/private links as public proof |
| Visual ML | Supported locally and historically executed | YOLOX-S ONNX provider, model cards, validation/work logs | Prompt 12 did not rerun real inference | “Trained YOLOX-S ONNX CPU inference is available locally.” | Hosted YOLOX inference |
| RAG / retrieval | Supported with qualification | Pinned BGE, heading-aware chunks, FTS, pgvector, RRF, extractive answers | Public companion demo absent | “Hybrid retrieval with deterministic citation-grounded extraction; no generative LLM.” | Naive generative RAG, Graph RAG, Self-RAG, Corrective RAG, agentic RAG or reranking |
| MCP built | Supported | One official-SDK ThreadEye Evidence MCP server | None for local claim | “Built one read-only MCP server exposing four tools and three sanitized resources.” | Two servers because it has two transports |
| MCP used | Supported locally | Official stdio and authenticated HTTP clients; UI calls HTTP MCP | No external cross-project consumer | “The same server was genuinely used through stdio and authenticated Streamable HTTP.” | Public deployment, complete OAuth or reuse bonus |
| Local LLM | Unsupported | No generative model exists | Would require separately authorized implementation and evidence | “Not implemented; answering is deterministic extraction.” | Embeddings as local LLM execution |
| Data lifecycle | Supported as development controls | Allowlist, authorization, hash, sanitization, provenance, versioning, synthetic corpus | Production governance not validated | “Approved synthetic evidence is hashed, sanitized, chunked, versioned and served read-only.” | Production-data compliance certification |
| Security | Supported within localhost boundary | Auth scope, read-only DB, input/citation tests, HTTP negatives | No TLS/public OAuth/distributed controls | “Security-tested localhost demonstration with fail-closed authorization and read-only DB.” | Production-ready security or comprehensive injection immunity |
| AI-native tooling | Supported as developer assistance | Claude Code/Codex disclosure, prompt library, CI, Make, Kaggle logs, Vercel script | Complete member IDE/tool disclosure | “AI coding assistance and training/deployment tooling are documented separately from runtime AI.” | Make.com, Claude Artifacts, LangGraph/CrewAI or formal AI-DLC without evidence |
| Reliability | Supported with explicit history | QA and reliability artifacts | Independent human label review absent | Report 5/10 → 8/10, known 9/10, fresh 10/12 → examined 12/12 | General 100% accuracy |
| Team / readiness | Partially supported | CODEOWNERS and review policy | Team leader approval, CI on PR, submission links | State exact review and access status | Approved PR, green GitHub CI or merged status |

Historical screenshot value: **133/215** (`Story 30`, `Proof 0`, `AI 69`, `Data 15`, `Ready 19` were visible in the
historical screenshot). These values are historical only and are not an authoritative current rubric.

## Official-source conditions that affect every claim

- The video is exactly three minutes under the current public preliminary rule.
- Demonstrations and results must not be fabricated or misleading.
- AI tools, models, data sources, prompts and external contributions must be explainable and documented.
- Lawful data sources and responsible privacy, bias, transparency and safety practices are required.
- Organizers may request clarification or additional verification.
