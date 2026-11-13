# Prompt 07 Security and Reliability Evaluation

## Scope and baseline

Prompt 07 preserves the original 35-query retrieval dataset, 44-case answer dataset, BGE thresholds
(`0.62`, `0.70`, `0.015`, lexical overlap `1`, meaningful tokens `2`) and all seven protected ThreadEye core hashes.
The new controls are decision rules and integrity checks; thresholds were not tuned on the final holdout.

The pre-implementation audit found that malformed and Unicode-obfuscated questions could escape as exceptions,
question echo was not independently sanitized, stored chunk hashes were trusted rather than recomputed at citation
time, optional retrieval filters were not all rechecked during citation validation, and backend errors lacked a safe
failure-stage/degraded-mode contract. Prompt 07 addresses those gaps. No regression was observed on the original two
benchmarks; the synthetic corpus and heuristic defenses remain the principal limitation.

Five fictional documents exercise indirect instructions, fake roles/code blocks/hidden text, conflicts, keyword
stuffing, semantic decoys, fake citations and spoofed metadata. They require the existing manifest approval and exact
`PROMPT-07-SECURITY-FIXTURES` intended-use authorization, then enter a separate
`threadeye-security-evidence-v1` / `prompt07-test-only` retrieval scope. No real document or credential is included.

## Reproduction

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence index-security-fixtures --offline-model
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-security \
  --split development --offline-model --format json
PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-security \
  --split final_holdout --offline-model --format json

THREADEYE_RUN_MODEL_TESTS=1 THREADEYE_RUN_DB_TESTS=1 \
  PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The actual runs used PostgreSQL 17, pgvector 0.8.7, FastEmbed 0.9.1 and pinned
`BAAI/bge-small-en-v1.5` revision `aa8f8b060edb00e03bfdd08813a2949946c8ba55` on CPU.

## Independent dataset and results

`evaluation/security-v1.json` contains 60 expected outcomes fixed before execution: 30 development and 30 final
holdout cases. Each split has 8 answerable cases and 22 unsupported, unsafe, malformed, unauthorized, adversarial or
failure cases. The final labels were not used for tuning.

The first independent final-holdout execution produced 27/30 exact outcomes. Two valid paraphrases were falsely
rejected because ordinary lowercase hyphenated phrases were misclassified as technical identifiers, and the citation
fault case did not always mutate the chunk ultimately selected. No threshold was changed. The identifier recognizer
was restricted back to uppercase technical forms, and the fault harness now mutates every candidate so the selected
path is deterministically exercised. Regression tests cover both defects. The post-fix rerun improved to 29/30;
one genuinely novel evidence-bundle paraphrase still conservatively abstained for insufficient relevance. The table
below reports that non-perfect result rather than tuning on the holdout.

| Metric | Development | Final holdout |
|---|---:|---:|
| Answerability accuracy | 30/30 | 29/30 |
| Correct abstention | 22/22 | 22/22 |
| False answers | 0/22 | 0/22 |
| False abstentions | 0/8 | 1/8 |
| Citation validity | 8/8 | 7/7 |
| Citation-source correctness | 8/8 | 7/7 |
| Unsupported claims | 0/8 | 0/7 |
| Authorization violations | 0/30 | 0/30 |
| Cross-corpus leakage | 0/30 | 0/30 |
| Direct prompt-injection attack success | 0/2 | 0/2 |
| Failure-mode correctness | 7/7 | 7/7 |
| Structured error correctness | 22/22 | 22/22 |
| Runtime failures | 0 | 0 |
| Average latency | 49.632 ms | 39.963 ms |
| P95 latency | 62.448 ms | 59.818 ms |

The original answer benchmark remained 44/44 exact outcomes with zero false answers, false abstentions, unsupported
claims or runtime failures. The original retrieval benchmark remained 35 queries with zero per-query failures;
hybrid Hit@1 was `0.90625`, Hit@3/5 and Recall@5 were `1.0`, and MRR was `0.947917`. Hybrid/vector no-result
accuracy remains `0.0` because nearest-neighbor retrieval always returns an authorized neighbor; answer sufficiency,
not vector retrieval, is the fail-closed no-answer boundary.

All 139 automated tests passed with genuine model and database flags enabled, with zero failures and zero skips.

## Failure isolation

Database unavailable, database timeout, stopped companion service, embedding unavailable, keyword failure, vector
failure, incompatible profile and citation tampering were simulated with in-process wrappers. They never stop the
container, delete a volume, alter stored rows or touch ThreadEye. PostgreSQL/model integration itself was exercised
against real local infrastructure. Every injected failure returned no factual answer. Hybrid branch failures were
reported as failures with `degraded: false`, never as successful hybrid retrieval.

The original ThreadEye application remains architecturally independent: the companion has no imports from it, uses a
dedicated loopback database/user/volume, and all protected hashes match the Prompt 02 baseline.

## Resolved weaknesses

- Malformed, hidden-control, mixed-script, oversized and invalid-mode questions now return structured errors.
- Unsafe raw questions are sanitized before response echo.
- Citation validation recomputes stored chunk hashes, checks stored span length, all optional scope filters and a
  bounded citation count.
- Exact identifiers, domain anchors and obvious keyword stuffing add conservative false-acceptance guards.
- A detected instruction attack quarantines every retrieved chunk from the same source, preventing a benign title or
  sibling chunk from becoming an answer path.
- Failure responses disclose a safe stage and explicitly deny degraded hybrid success.
- Evaluation reports numerators, denominators, attack/leakage/failure measures, average latency and P95.

## Remaining risks and trade-offs

Pattern and heuristic defenses are incomplete. Novel prompt injection, low-rate poisoning, single-script confusables,
valid domain terminology outside the small anchor set and unusual paraphrases can be missed or falsely rejected.
Conflicts cause abstention rather than resolution. Citation checks establish exact extractive provenance, not general
semantic truth. A human must review the 16 supported evaluation answers. Prompts 08–09 subsequently added local MCP
stdio and authenticated loopback HTTP with deadlines and per-process limits, but there is still no public/distributed
rate limiter, retry/high-availability layer, generative LLM, reranker, local LLM, companion frontend or production
integration. These synthetic results must not be generalized into a production security guarantee.
