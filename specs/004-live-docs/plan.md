# Plan

Use a versioned JSON document in the existing settings table: no migration or
process-local persistence. Serve a public, fail-closed, uncached API and separate
settings.manage-protected admin GET/PUT/preview. Serialize edits with a database
advisory lock, compare revisions and audit content hashes. Validate bounded
images using Pillow, strip metadata and resize to 256px JPEG. No remote fetches.

Use a standalone /docs client page outside the authenticated AppShell; only this
exact page bypasses the optimistic cookie redirect. Backend gates every public
read. The /admin/docs editor stays behind authentication/settings permission.
Render plain text and code-native diagrams. Keep live API/runtime/count data
computed from current state, distinct from authored narrative and stored test
metrics. Support existing locale/theme controls and no-cache refetching.

Constitution: preserve inspection/model identities and business rules; expose
aggregates only; do not claim automatic retraining, factory impact or unavailable
LLMs. Update generated OpenAPI/types; verify gates on disposable PostgreSQL and
browser fixtures, plus existing security/inspection regressions.
