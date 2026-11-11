# Grounded Extractive Evidence Answering

## Scope and architecture

Prompt 06 implements an evidence-answering layer, not an LLM generator:

```text
validated question
  → request safety policy
  → exact authorized-scope count
  → Prompt 05 hybrid retrieval
  → multi-signal evidence selection and sufficiency
  → deterministic sentence extraction
  → citation, span, authorization and claim validation
  → answered response or explicit abstention
```

`answer_mode` is always `extractive`. The future generator protocol records provider/model identity, context and
output limits, parameters, timeout, structured output and errors. Its only current implementation is explicitly
unavailable and raises `NotImplementedError`. No paid API, hosted model or local LLM was executed.

## Response and citation contract

Responses contain question, status, answer mode, answer, citations, supporting chunk IDs, retrieval mode/metadata,
abstention reason, limitations, corpus, embedding profile, processing versions, sufficiency signals and latency.
Successful answers and abstentions are structurally distinct.

Each citation contains source path/SHA-256, chunk ID/SHA-256, heading hierarchy, normalized start/end, processing
version, authorization reference, corpus version and exact excerpt. Validation proves that the chunk was among the
authorized retrieval results; all provenance fields match; the span lies inside the chunk; the stored sanitized text
matches the excerpt; the evidence is relevant; and the entire extractive answer equals the ordered cited excerpts.

Offsets refer to sanitized normalized Markdown text, not original raw bytes or page numbers.

## Sufficiency and abstention

Configuration `prompt06-dev-v1` was selected using only the 20 development cases and frozen before final held-out
evaluation:

- Minimum question content tokens: 2, except exact technical identifiers.
- Minimum semantic similarity: 0.62.
- Strong semantic similarity: 0.70.
- Minimum ambiguity margin: 0.015.
- Minimum lexical overlap: 1.
- Maximum supporting chunks: 2; the current conservative selector cites one chunk.

Evidence selection combines exact identifiers, PostgreSQL keyword evidence, lexical overlap, BGE similarity and
ambiguity. RRF and cosine values are not probabilities. Missing/weak/ambiguous evidence, contradictions, unauthorized
scope, invalid citation, backend failure and untrusted document instructions produce named abstentions.

Requests to reveal secrets, access production systems, obey prompt injections, override scoring, or approve/reject a
real roll are blocked before answer construction. The assistant may explain documented responsibilities but cannot
perform operational actions.

## Evaluation

`evaluation/answering-v1.json` was labeled before prediction review and retains the Prompt 05 retrieval dataset
unchanged. It contains 44 cases: 22 answerable and 22 unsupported/unsafe, split into 20 development and 24 held-out
cases. Categories include facts, paraphrases, identifiers, multi-sentence evidence, ambiguity, out-of-corpus,
contradiction, unauthorized filters, prompt injection, secrets, production access and roll-verdict overrides.

Development result: 20/20 answerability decisions, 10/10 correct abstentions, zero false answers/abstentions, citation
validity/precision/source correctness 1.0 and unsupported-claim rate 0.0.

The first held-out execution at `2026-11-11T13:37:41.188653+00:00` had zero false answers and 12/12 correct negative
abstentions, but failed closed on three exact-identifier positives because extraction attached an irrelevant second
sentence. The thresholds were not changed. A general claim-support fix restricted additional extracted sentences to
those with lexical support and added a regression test.

The post-fix held-out execution at `2026-11-11T13:39:50.327341+00:00` reported:

| Metric | Held-out result | Denominator |
|---|---:|---:|
| Answerability accuracy | 1.0 | 24 |
| Correct abstention rate | 1.0 | 12 negative |
| False-answer rate | 0.0 | 12 negative |
| False-abstention rate | 0.0 | 12 positive |
| Citation validity | 1.0 | produced citations |
| Citation precision | 1.0 | produced citations |
| Evidence-source correctness | 1.0 | 12 positive |
| Unsupported-claim rate | 0.0 | 12 answers |
| Structured-response validity | 1.0 | 24 |
| Average latency | 55.384 ms | 24 |
| Runtime failures | 0 | 24 |

These results cover a small fictional six-chunk corpus and deliberately scoped cases. Automatic checks establish exact
source support, not human-level semantic reasoning. All 12 positive answers remain reviewable in the JSON report.

## Real database demonstrations

- Supported identifier: `Which supplier lot is recorded for ROLL-NST-204?` returned `LOT-FX-17`, chunk
  `f53285a64a29b46ed7e52aad`, validated span 242–413.
- Semantic paraphrase: `Where is an incoming roll placed while it awaits checking?` cited Fabric Receiving and the
  quarantine-lane sentence.
- Unsupported: loom-maintenance interval retrieved neighbors but abstained `insufficient_relevance`; similarity
  `0.618403` was below the frozen minimum and had zero lexical overlap.
- Unauthorized: a nonexistent authorization reference returned `unauthorized` with no evidence.
- Embedded injection: the separately authorized fictional adversarial corpus retrieved chunk
  `dcafc09772cd36c5b08bba64` but abstained `untrusted_instruction_evidence` and did not echo or execute it.

## Commands

```bash
PYTHONPATH=src .venv/bin/python -m threadeye_evidence answer-evidence \
  --question 'Which supplier lot is recorded for ROLL-NST-204?' --offline-model --format json

PYTHONPATH=src .venv/bin/python -m threadeye_evidence evaluate-answers \
  --split held_out --offline-model --format json
```

## Limitations

- The corpus and evaluation are synthetic, small and domain-constrained.
- The relevance gate is heuristic and can conservatively abstain on valid novel paraphrases.
- Contradiction handling is conservative abstention, not resolution.
- Prompt-injection detection remains pattern/heuristic based even after Prompt 07 adversarial testing; it is not a
  complete classifier or security boundary for a future generative model.
- No LLM generation, reranker, answer rewriting, MCP, UI or public endpoint exists.
