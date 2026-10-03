# Ethical safeguards (documented)

The judging band 16–20 for *Real-World Impact + Ethical AI* needs **documented** safeguards. Each
principle below (from the team's Workflow PDF §12) maps to a concrete product mechanism, with its
status. Owner: D. Completed in M6; kept current every milestone.

| Principle | Mechanism in ThreadEye | Status |
|---|---|---|
| **Humans decide.** AI suggests, the inspector confirms; roll rejection is a human decision | Every defect is `pending` until confirmed, rejected or reclassified. Finalize is blocked while anything is pending. BORDERLINE and any override need a supervisor reason | Designed (contract v0), built M2/M4 |
| **Worker dignity, no surveillance** | Inspector correction statistics are used for training only. The inspector role has no access to per-inspector dashboards (`dashboard.own_shift` only). The camera points at the fabric, and the sampler avoids frames with the hand in view | RBAC enforced (M0); sampler M1 |
| **Buyer design confidentiality** | Edge-first: images never leave the factory. The app containers have no internet route (`make verify-offline`). Any future external API is off by default and needs an admin consent record | Enforced (M0) |
| **Transparency** | Every detection shows its provider, an explanation and a box. `confidence` is `null` unless calibrated (no invented "96 % sure"). A SIMULATED banner shows on every screen and report | Banner + provider contract (M0) |
| **Honest claims** | "4-point inspection report", never "ASTM/AQL compliant". Simulated results are never presented as factory results. No metric is shown unless measured | Report base + empty-state dashboard (M0) |
| **Accountability** | Append-only, SHA-256 hash-chained audit log, with a DB trigger blocking edits and a chain-verify endpoint and page | Enforced (M0) |
| **Bias across fabrics** | Benchmark reports per-segment metrics (dark/light/patterned via `datasets.fabric_attrs`) | Planned M6 |
| **Learning from mistakes** | Rejections and manual additions become `label_samples`, split by source image. Evaluation refuses training data | Planned M4–M6 |
| **Data provenance** | PROVENANCE.md lists every dataset, licence, font and tool | Maintained from M0 |
