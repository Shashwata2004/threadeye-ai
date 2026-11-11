"""Serving authorization kept independent from document-ingestion approval."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetrievalAccessPolicy:
    corpus_id: str
    access_policy: str
    document_classification: str
    authorized: bool

    def __post_init__(self) -> None:
        for field_name in ("corpus_id", "access_policy", "document_classification"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string")
        if self.authorized and (
            self.corpus_id == "unassigned"
            or self.access_policy == "deny"
            or self.document_classification == "unclassified"
        ):
            raise ValueError("authorized retrieval requires an explicit corpus, policy, and classification")


DENY_RETRIEVAL_POLICY = RetrievalAccessPolicy("unassigned", "deny", "unclassified", False)

SYNTHETIC_EVALUATION_POLICY = RetrievalAccessPolicy(
    "threadeye-synthetic-evidence-v1",
    "prompt05-test-only",
    "synthetic_test_fixture",
    True,
)

ADVERSARIAL_EVALUATION_POLICY = RetrievalAccessPolicy(
    "threadeye-synthetic-adversarial-v1",
    "prompt06-test-only",
    "synthetic_security_fixture",
    True,
)
