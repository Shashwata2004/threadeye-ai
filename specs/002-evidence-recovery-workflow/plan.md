# Plan: Evidence Recovery Workflow

Use the official LangGraph StateGraph API with shared request/response state,
primary_answer, keyword_recovery and finalize nodes, and a conditional edge.
Reuse EvidenceAnswerEngine rather than duplicate its authorization and citation
logic. Pin LangGraph in an optional agentic extra (Python >=3.10), keep imports
lazy, and expose the workflow in the existing CLI.

## Constitution Review

- Traceability: include framework version, node outcomes and recovery disclosure.
- Authority: each attempt executes existing read-only authorization checks.
- Provenance: existing citations remain validated and source filters unchanged.
- Compatibility: opt-in companion CLI; no main app API/schema/deployment changes.
- Evidence: run actual graph code with deterministic retrieval fixtures; label
  these as orchestration tests, not live database or model quality evaluation.

## Validation

Test normal answers, successful/failed recovery, authorization revocation,
policy/input rejection, weak evidence, keyword errors and citation failures.
Run existing answering and retrieval tests for regressions.
