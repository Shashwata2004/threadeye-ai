# Threat Model

Prompt 03 adds synthetic, approval-gated sanitization and chunking. Future mitigations remain requirements,
not current capabilities.

| Threat | Impact | Current mitigation | Required future mitigation | Relevant test |
|---|---|---|---|---|
| Path traversal | Read files outside the approved checkout | Reject absolute paths and `..`; resolve beneath canonical root | Retain validation at every ingestion/tool boundary | `test_path_traversal_is_rejected`, `test_absolute_path_is_rejected` |
| Symlink escape | Manifest path redirects to an external file | Reject symlinks and verify the resolved path remains under the root | Revalidate immediately before every read; run with least filesystem privilege | `test_symlink_escape_is_rejected` |
| Secret leakage | Credentials enter snapshots, an index, or responses | Supported patterns are redacted before persistence; private-key marker fails closed; raw values absent from safe stats | Entropy scanning, manual review and domain-specific detectors before real ingestion | Sanitization and snapshot non-disclosure tests |
| Unauthorized ingestion | Inventory approval is mistaken for AI-use approval | Independent ingestion flag, team-authorization record and exact intended-use match; all real flags false | Signed review workflow and corpus-version approvals | `test_authorization.py` |
| Prompt injection in documentation | Document text manipulates a future model/tool | Markdown and fenced code remain inert data and are never executed | Instruction hierarchy, output validation and adversarial evaluation once a model exists | Normalization non-execution test; future model evaluation not implemented |
| Future MCP tool misuse | A tool exposes private data or performs writes | MCP is not implemented | Small explicit read-only registry, scoped auth, negative authorization and write tests | Future MCP authorization tests; not implemented |
| Production database access | AI extension changes or leaks operational records | No database dependency, configuration, driver, or connection | Separate read-only replica/role only if explicitly authorized; deny writes in tests | `test_inventory_requires_no_network_or_database` |
| Misleading AI fabric decisions | Generated text is treated as official verdict | Contract states no inventory/AI output is authoritative; no generator exists | Cite saved deterministic result, show limitations, require human review, abstain | Future grounded-answer/abstention tests; not implemented |
| Dependency/deployment coupling | Companion changes break ThreadEye | Separate project, runtime standard library only, no ThreadEye imports | Separate lock, containers, CI and failure-isolation checks | ThreadEye protected-file hash comparison |
| Licensing/redistribution | Restricted material is embedded or published | Real ingestion flags remain false; only fictional fixture output is persisted | Legal/team approval, redaction, corpus export policy | Real-manifest rejection test; future release audit |
