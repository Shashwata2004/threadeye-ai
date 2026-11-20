# Feature Specification: Evidence Recovery Workflow

**Created**: 2026-11-20

## Goal

Use LangGraph to orchestrate a bounded recovery path in the evidence assistant.
A vector backend failure may trigger one keyword-only answer attempt. Each
attempt retains the original authorization, policy, sufficiency and citation gates.
No LLM, QC decisions, production writes or unrestricted tool execution are added.

## Acceptance Scenarios

1. Successful primary answers retain their citations and record one attempt.
2. An identified vector retrieval failure routes once to keyword retrieval with
   the same filters and limits, reporting degraded mode and both attempt outcomes.
3. Invalid input, denied scope, policy rejection, weak evidence and invalid
   citations cannot trigger retries that bypass their respective gates.
4. Failed recovery stops after two attempts, and authorization is checked again.
5. Users select the workflow explicitly through answer-evidence --orchestration
   langgraph; the existing default and base installation remain unchanged.

## Evidence

See plan.md, tasks.md and the companion README for implementation and validation.
