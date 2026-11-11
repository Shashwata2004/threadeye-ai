# Threat Model

Prompt 02 covers local metadata/hash inventory only. Future mitigations below are requirements, not current
capabilities.

| Threat | Impact | Current mitigation | Required future mitigation | Relevant test |
|---|---|---|---|---|
| Path traversal | Read files outside the approved checkout | Reject absolute paths and `..`; resolve beneath canonical root | Retain validation at every ingestion/tool boundary | `test_path_traversal_is_rejected`, `test_absolute_path_is_rejected` |
| Symlink escape | Manifest path redirects to an external file | Reject symlinks and verify the resolved path remains under the root | Revalidate immediately before every read; run with least filesystem privilege | `test_symlink_escape_is_rejected` |
| Secret leakage | Credentials enter metadata, an index, or responses | Exact Markdown allowlist; hidden/config/key/dump formats rejected; no contents emitted | Content secret scanning and human approval before ingestion | `test_secret_like_paths_are_rejected`, inventory content-absence tests |
| Unauthorized ingestion | Inventory approval is mistaken for AI-use approval | Separate `inventory_approved` and `future_ingestion_approved`; all future flags false | Signed review workflow and corpus-version approvals | `test_manifest_defaults_future_ingestion_to_false` |
| Prompt injection in documentation | Document text manipulates a future model/tool | Current inventory never executes or interprets document text | Treat retrieved text as data; instruction hierarchy, output validation, adversarial evals | Future prompt-injection evaluation; not implemented |
| Future MCP tool misuse | A tool exposes private data or performs writes | MCP is not implemented | Small explicit read-only registry, scoped auth, negative authorization and write tests | Future MCP authorization tests; not implemented |
| Production database access | AI extension changes or leaks operational records | No database dependency, configuration, driver, or connection | Separate read-only replica/role only if explicitly authorized; deny writes in tests | `test_inventory_requires_no_network_or_database` |
| Misleading AI fabric decisions | Generated text is treated as official verdict | Contract states no inventory/AI output is authoritative; no generator exists | Cite saved deterministic result, show limitations, require human review, abstain | Future grounded-answer/abstention tests; not implemented |
| Dependency/deployment coupling | Companion changes break ThreadEye | Separate project, runtime standard library only, no ThreadEye imports | Separate lock, containers, CI and failure-isolation checks | ThreadEye protected-file hash comparison |
| Licensing/redistribution | Restricted material is embedded or published | Inventory stores hashes/metadata only; future ingestion false; caveats retained | Legal/team approval, redaction, corpus export policy | Manifest approval/caveat tests; future release audit |
