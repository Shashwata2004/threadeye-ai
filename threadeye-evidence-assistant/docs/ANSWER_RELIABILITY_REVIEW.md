# Answer Reliability Review

Recorded: 2026-11-13

Scope: Prompt 11R, fictional approved synthetic evidence only

Decision: **bounded remediation gate passed after preserving a failed first fresh run and correcting its general defects**

## Executive summary

Prompt 11R reproduced the two remaining Prompt 11 QA defects. The unsupported spindle-speed answer was caused by a
section-heading match and semantic similarity being accepted as factual support for an unrelated sentence. The
comparison question was a false abstention because the correct chunk ranked fourth at cosine similarity `0.60225866`,
below the unchanged `0.62` sufficiency floor.

The correction requires relevance in an actual answer-bearing statement, not merely a heading; checks explicit
inference relationships; and verifies that requested typed numeric/percentage values actually appear outside an
identifier. It does not lower similarity thresholds, add a generative model, hard-code case IDs, or change the
corpus. The known QA regression is now 9/10: zero false answers, one deliberately retained false abstention, and 4/4
valid returned citations.

A preregistered 24-case evaluation was split into 12 development and 12 fresh-holdout cases. The primary untouched
fresh run was **10/12**, not 12/12: it found one unsupported answer and one false abstention. That result is preserved.
General typed-value and capability-question corrections were added; the explicitly examined regression then passed
12/12. The final all-flags companion suite passed **190/190** with no failures or skips.

## Starting state and boundaries

- Required branch: `feature/threadeye-evidence-assistant`
- Verified starting HEAD: `c5405a82910030f697470e2347dfba7949145634`
- Starting tree: clean
- Prompt 02 ancestry baseline: `a0c7141`
- All Prompt 11R tracked changes remain under `threadeye-evidence-assistant/`.
- No production system or real document was accessed.
- No push, merge, rebase, PR, deployment, OAuth change, or Prompt 12 work occurred.
- The four historical evaluation files were not edited.

The unmodified baseline initially could not run because the isolated companion database container was stopped and the
read-only MCP role environment was absent. The existing loopback service was restarted without deleting its volume,
the supported role setup was run, and the unmodified all-flags baseline passed 180/180. This was an environment
recovery, not a code change.

## Reproduced Prompt 11 failures

### QA11-N01 — unsupported answer

- Question: `What spindle speed does the fictional weaving machine use?`
- Expected: `insufficient_evidence / insufficient_relevance`
- Actual before correction: answered `This document is synthetic.`
- Retrieved ranks, chunk IDs and cosine scores:
  1. `221d1bcaa4d4ec4927dd6b4b` — `0.62567166`
  2. `f53285a64a29b46ed7e52aad` — `0.57927409`
  3. `e1569f1c868b8657f838f33e` — `0.50636437`
  4. `01738d4176ee251839337d2a` — `0.50496623`
  5. `59e04794f6ffa0ba4b96508e` — `0.47127342`
- Retrieval was vector-only; no keyword match existed.
- Sufficiency selected rank 1 because `0.62567166` exceeded `0.62` and the heading contributed the generic word
  `fictional`.
- Extraction selected the first safe sentence despite zero question overlap in that sentence.
- Citation hash, source, span, authorization and corpus validation all passed.
- Authorization context: corpus `threadeye-synthetic-evidence-v1`, policy `prompt05-test-only`, authorization
  `PROMPT-04-SYNTHETIC-VECTOR-FIXTURE`, pinned BGE profile.
- Confirmed cause: misleading similarity plus missing question-to-statement relationship; authentic citation
  provenance was mistaken for semantic factual support.
- General correction: require support in an answer-bearing statement and exclude headings from claim relevance.

### QA11-P03 — false abstention

- Question: `What allows two fictional rolls with unequal inspected areas to be compared?`
- Expected: answered from `Four-Point Scoring Explanation`.
- Actual: `insufficient_evidence / insufficient_relevance`.
- Retrieved ranks, chunk IDs and cosine scores:
  1. `e1569f1c868b8657f838f33e` — `0.65477679`
  2. `c27ae52335deedd401081a9f` — `0.63923498`
  3. `f53285a64a29b46ed7e52aad` — `0.61147362`
  4. `01738d4176ee251839337d2a` — `0.60225866`
  5. `59e04794f6ffa0ba4b96508e` — `0.57232012`
- Retrieval was vector-only; no keyword match existed.
- Sufficiency correctly selected rank 4 by lexical relationship, but `0.60225866` remained below the frozen `0.62`
  threshold. Extraction and citation validation therefore did not run.
- Confirmed cause: a novel paraphrase and vector ranking placed generic evidence above the correct scoring chunk.
- Decision: retain this conservative false abstention. Lowering or bypassing the examined threshold would increase
  unsupported-answer risk. The threshold was not tuned on the holdout.

## Corrective changes

1. Content terms receive small deterministic inflection normalization; identifiers remain exact.
2. Sufficiency requires overlap in an actual statement. Heading text can aid retrieval but cannot establish factual
   support.
3. Explicit inference questions such as “does X prove Y?” require both sides in one evidence statement.
4. Numeric and percentage requests require a corresponding typed value after identifiers are removed from the value
   check.
5. Citation relevance uses cited excerpts rather than section headings.
6. Third-person capability-boundary questions may reach the evidence engine, while operational approval commands
   remain blocked.
7. Regression tests cover heading-only relevance, frozen-threshold preservation, inference relationships, typed
   percentages, capability questions, citation relevance, dataset immutability, split integrity, and real database
   development evaluation.

These are general, fail-closed rules. No benchmark question, expected answer, case ID, or synthetic corpus passage is
embedded in runtime logic.

## Historical evaluation preservation

| Historical file | SHA-256 after Prompt 11R |
|---|---|
| `evaluation/retrieval-v1.json` | `39eb28be9fd2910f433360b720e05b49465b44cc9ee05b4269d24b23ff435df8` |
| `evaluation/answering-v1.json` | `1391613a108830e5c540a776dd0d0c3c478332e9cefb1e2473785a18ed470643` |
| `evaluation/security-v1.json` | `3481f9805091c031ba364cf17e3fcedac197b1d6dbf48d1fc220438d88fe5fbb` |
| `evaluation/qa-holdout-v1.json` | `8ee8907a4c57fae22467d23ef1d3a36ec46180d70fe8bb238fee7d8ad8f016ea` |

Prompt 11's 5/10 untouched result and 8/10 examined result remain historical evidence. Prompt 11R did not relabel or
rewrite them.

## New evaluation method

`evaluation/answer-reliability-v1.json` contains 24 new questions: 12 development and 12 fresh holdout, each with six
positive and six negative cases. It covers direct answers, paraphrases, unsupported attributes, identifier confusion,
contradiction, misleading neighbors, similar-but-different facts, qualifiers, unsupported inference, and secret
requests. Labels and expected support terms were written before execution. Threshold tuning is forbidden.

- Dataset SHA-256: `91eb6b0b58b0c2b82607cd8dfdf525ba70cbba74c39ad211ed62336c3773338b`
- Pre-first-run corrective code SHA-256: `a594dae4aaf47ddd20140b7ea79825ab10d00ca9223cd6604a7e2e56fbfa24ae`
- Final corrective code SHA-256: `f93d70f45e8eec0ad61ae4a1cf1e7d51c9b7da61a4b0b237adf1fd21047618a2`
- Independent human label review: unavailable.

This dataset was automatically authored from the small approved corpus and inspected during implementation. It is not
described as fully independent. Technical citation validity and semantic support are separate metrics.

## Results and metrics

| Metric | Development | Fresh primary untouched | Fresh examined regression |
|---|---:|---:|---:|
| Overall answerability accuracy | 12/12 | 10/12 | 12/12 |
| Correct abstention | 6/6 | 5/6 | 6/6 |
| False answers | 0/6 | 1/6 | 0/6 |
| False abstentions | 0/6 | 1/6 | 0/6 |
| Citation validity | 6/6 | 6/6 | 6/6 |
| Semantic evidence support | 12/12 | 10/12 | 12/12 |
| Authorization violations | 0/12 | 0/12 | 0/12 |
| Unsupported claims | 0/12 | 1/12 | 0/12 |
| Positive-answer coverage | 6/6 | 5/6 | 6/6 |
| Runtime failures | 0 | 0 | 0 |

The primary fresh result found:

- `REL1-H-N03`: `DEF-HOLE-04` and a “confidence note” were returned for a requested numerical confidence percentage,
  although no percentage existed. Citation integrity was valid; semantic support was false.
- `REL1-H-P05`: an informational question about whether automated retrieval can replace a supervisor was incorrectly
  rejected as a verdict request.

The first result remains the primary untouched score. The 12/12 rerun is an examined post-fix regression and must not
be presented as independent. The sample is too small for strong confidence bounds, is synthetic, and says nothing
about factory-production accuracy.

## Genuine integration and regression

Final command enabled all five flags:

```bash
THREADEYE_RUN_MODEL_TESTS=1 \
THREADEYE_RUN_DB_TESTS=1 \
THREADEYE_RUN_MCP_TESTS=1 \
THREADEYE_RUN_HTTP_TESTS=1 \
THREADEYE_RUN_UI_TESTS=1 \
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Result: **190 passed, 0 failed, 0 skipped** in 10.870 test seconds.

The suite genuinely exercised pinned BGE embeddings, PostgreSQL/pgvector, keyword/vector/hybrid retrieval, extractive
answers, citation validation, adversarial security evaluation, the `threadeye_evidence_mcp` read-only role, official
MCP stdio client, two authenticated official HTTP clients, and the judge UI gateway. SELECT was allowed for the MCP
role; INSERT, UPDATE, DELETE, TRUNCATE, DDL, temporary tables, role creation and database creation remained denied.

No original backend/frontend test was rerun because Prompt 11R changed no original file. Prompt 11's recorded 213
backend-unit, 77 backend-integration (one ffmpeg skip), and passing frontend checks remain the latest original-app test
evidence. Real YOLOX ONNX inference was not rerun.

## Core integrity and approvals

All seven protected paths match their Prompt 02 baseline SHA-256 values. The wider diff from `a0c7141` contains no
path outside `threadeye-evidence-assistant/`. The six real-document manifest entries still have
`future_ingestion_approved: false`. Security and authorization tests remain passing; no real source was ingested.

## Residual risks and release gate

- Known QA coverage remains 4/5 because the comparison paraphrase safely abstains.
- The first fresh result was 10/12 and must remain visible even though its two defects were corrected.
- Rule-based extraction cannot prove arbitrary natural-language entailment.
- Synthetic evaluation, a small sample, and absent independent human review limit confidence.
- Citation integrity proves exact authorized provenance, not semantic correctness by itself.

The initial fresh false answer blocked readiness until the general typed-value fix and regression were complete. The
identified defect no longer reproduces, the examined fresh regression has zero unsupported claims, all integration
checks pass, protected hashes match, and no authorization boundary was weakened. The bounded Prompt 11R remediation
gate therefore passes for a local companion commit. This is not a claim of zero future error, production readiness,
or factory accuracy. Prompt 12 has not started.

Machine-readable evidence is in `docs/evidence/prompt11r-answer-reliability-results.json`.
