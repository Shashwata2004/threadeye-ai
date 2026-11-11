# Fictional Mill Evidence Packet

This document is synthetic. It describes the imaginary Northstar Textile Lab and contains no ThreadEye production records, customer data, private documents, or operational measurements.

## Fabric Receiving

In the fictional receiving workflow, an operator records a roll identifier, declared length, fabric construction, supplier lot, and arrival timestamp. The operator places the roll in a quarantine lane until visual inspection is complete. A synthetic receiving record links the roll to later inspection evidence without changing any source measurement.

## Defect Classification

The training example distinguishes holes, stains, slubs, broken yarn, and edge damage. Each fictional observation includes a defect label, location, confidence note, and image reference. Classification evidence remains separate from acceptance decisions so a reviewer can audit how a label was assigned.

## Four-Point Scoring Explanation

The example scoring guide assigns one to four penalty points according to a fictional defect's longest dimension. The score is aggregated over an inspected area and normalized for comparison. This paragraph is explanatory test content only; it does not reproduce or alter ThreadEye's buyer-specific scoring implementation.

## Quality Inspection Evidence

An evidence bundle contains the sanitized observation, inspection timestamp, synthetic roll reference, reviewer status, and content hash. Hashes make later changes detectable. The bundle never stores credentials, raw private documents, or an unapproved source file.

## Supervisor Review

The fictional supervisor reviews flagged observations, confirms or rejects the proposed classification, records a reason, and preserves the prior evidence. Approval is explicit and traceable. Automated retrieval may surface the sanitized record, but it cannot approve a roll or replace the supervisor's decision.
