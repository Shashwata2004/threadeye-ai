# Residual Risks and Release Decisions

## Technical and evidence risks

| Risk | Current control/evidence | Required next action |
|---|---|---|
| Original product real-model path not rerun in Prompt 12 | Model/provider provenance and earlier reports exist; hosted demo is disclosed as simulated | Rehearse real local YOLOX with a non-production environment and record exact mode |
| Companion answer errors or conservative abstention | Exact extraction, citation and sufficiency policy; honest first/examined history | Independent human labels and broader adversarial/domain sets; human review for consequential use |
| Citation correctness mistaken for semantic truth | Exact-span validation plus rule-based statement checks | Review meaning separately; citation presence alone is insufficient |
| Synthetic/small evaluation overgeneralization | Results label fictional sets and examined reruns | Do not extrapolate factory accuracy; execute a controlled pilot |
| Local access mistaken for production auth | Loopback binding, scoped tokens, read-only DB and negative tests | Add production identity, TLS, secret management, revocation, distributed limits and security review before remote use |
| Rule-based entailment blind spots | Conservative abstention and 29/30 security holdout history | Expand independently authored cases; review policy failures |
| External proof incomplete | Link audit explicitly marks missing/blocked items | Complete YouTube/Figma, repository access and signed-out hosted-flow checks |
| Deployed revision unknown | Web/API HTTP 200 only | Bind deployment metadata to a reviewed commit and test authenticated flow |
| Real document/privacy boundary | All six real approvals false; fictional corpus and read-only service | Keep false until separate owner/legal authorization; never connect production Supabase |
| License/redistribution uncertainty | Provenance records sources and open question | Resolve AITEX/other asset permissions before public distribution |
| Business impact unvalidated | KPI/pilot plan exists | Conduct ethical factory pilot; report baseline, sample and uncertainty |
| Branch/base uncertainty | Merge-base and diff analysis complete | Team leader confirms base, publishing authority and expected CI |

## Security/privacy review outcome

- Evidence documents must contain no credential values, tokens, private keys, expanded database URLs, production data
  or private user/contract information.
- Screenshots used here contain the fictional companion UI and were visually reviewed; reviewers should repeat the
  privacy check before public release.
- Public artifacts must avoid workstation-specific absolute paths.
- Search/evaluation fixtures are synthetic; this does not make every third-party model/dataset license automatically
  redistributable.
- The security evaluation demonstrates specific tested controls, not immunity from prompt injection or all attacks.

## Separate readiness decisions

### READY FOR LOCAL TEAM REVIEW — YES

Passed: companion implementation, current all-flags suite, current browser workflow, evaluation reruns, protected
hashes, approval boundaries and evidence documentation. Human gates: technical/product/security/license review.

### READY TO PUBLISH FEATURE BRANCH — NO

Technically clean after the Prompt 12 commit, but explicit publishing authorization, confirmed PR base and final
secret/license review are still required.

### READY TO CREATE DRAFT PR — NO

The branch is local and unpublished; team-leader base approval, remote branch verification and repository access plan
are missing. A copy-ready body is available in `PR_READINESS.md`.

### READY FOR PUBLIC COMPETITION SUBMISSION — NO

Missing YouTube, Figma, verified judge repository access and final official-form/save/reload review. Hosted login/full
flow and deployed SHA are also unverified. Product and AI claims must receive team approval.

### READY TO MERGE — NO

No Draft PR or remote CI exists for this branch, and no team review/approval has occurred. Merge only after the
authorized base, CI, security/license review and review feedback are resolved.

## Human/external action list

1. Team leader confirms the PR base and authorizes publishing.
2. Product/ML owners rerun and record the original local trained-model demo without production data.
3. Design owner completes and signed-out tests the clickable Figma prototype.
4. Media owner records/uploads/signed-out tests the three-minute YouTube video.
5. Repository owner grants judges access or approves a reviewed public release.
6. Deployment owner verifies the hosted authenticated workflow and revision.
7. License/data owners resolve redistribution and consent questions.
8. Team reviews live official fields, saves/reloads if supported, and an authorized human submits.
9. After approval, publish one branch, create one Draft PR, inspect CI, review and merge through normal governance.
