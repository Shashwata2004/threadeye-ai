# Submission Link Audit

Checked 2026-11-13. An HTTP response proves reachability only; it does not prove the deployed revision, authentication
flow, complete behavior or claim quality. Recheck every submitted link from a signed-out browser immediately before
submission.

| Proof item | URL / location | Purpose | Access / authentication | Current result | Missing action | Owner |
|---|---|---|---|---|---|---|
| Original product web | `https://threadeye-web.vercel.app` | Hosted product workflow | Public landing response; app auth may be required | HTTP 200; workflow and deployed SHA not verified; detector disclosed as simulated | Team-owned signed-out and role-flow test; confirm demo credentials/instructions | Team leader / deployment owner |
| API health | `https://threadeye-api.vercel.app/health` | Hosted API availability | Public health endpoint | HTTP 200; not a full API/security test | Confirm response, revision and intended public disclosure | Backend/deployment owner |
| GitHub repository | `https://github.com/Shashwata2004/threadeye-ai` | Source and provenance | Apparently private or unavailable unauthenticated | HTTP 404 to unauthenticated check | Confirm canonical URL, visibility and judge access; never expose secrets | Repository owner |
| Feature branch | No public URL | Evidence Assistant source | Local only | `feature/threadeye-evidence-assistant` is unpublished | After approval, push and verify remote; then create one Draft PR | Team leader / branch author |
| YouTube demo | `MISSING` | Required three-minute prototype video | Must meet organizer access rule | Not uploaded or verified | Record, disclose modes/limits, upload and signed-out test | Team media owner |
| Figma prototype | `MISSING` | Clickable original-product UX | Viewer link required | No link or interactions verified | Complete required flow, share view-only and signed-out test | Design owner |
| Evidence Assistant | `http://127.0.0.1:8770` | Local technical evidence demo | Local operator code; not remotely accessible | Current real Chrome workflow passed locally | Provide supervised local setup; do not list as public URL | Technical presenter |
| Technical evidence pack | `threadeye-evidence-assistant/docs/cloudcamp/README.md` | Claim/test/reproduction evidence | Repository access required | Present locally | Becomes reviewable only with authorized repo/branch access | Branch author |
| Model/training provenance | Root `PROVENANCE.md` plus referenced work logs | Dataset/model/tool disclosure | Repository and external notebook permissions vary | Repository evidence exists; external access not comprehensively retested | Owner verifies notebook sharing and redistribution terms | ML owner |
| CloudCamp rules | `https://cloudcampbd.com/events/ai-builders-congress/policies/submission` | Official submission requirements | Public | HTTP 200; v1.1 shown as published 2026-05-12 | Recheck for changes before final submission | Submission owner |
| CloudCamp AI policy | `https://cloudcampbd.com/events/ai-builders-congress/policies/ai-usage` | Official AI/provenance conditions | Public | HTTP 200; v1.1 shown as published 2026-05-12 | Recheck for changes before final submission | Submission owner |

## High-impact blockers

1. Required YouTube video is missing.
2. Figma prototype link and interactions are missing.
3. GitHub is not accessible to an unauthenticated reviewer and the feature branch is unpublished.
4. Hosted login/full workflow and deployed revision are unverified.
5. Evidence Assistant has no public deployment by design; use a supervised local demonstration.

Do not paste access codes, passwords, database URLs, private tokens or production data into link notes.
