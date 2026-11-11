from __future__ import annotations

import unittest
from dataclasses import replace

from threadeye_evidence.answering.abstention import SufficiencyConfig
from threadeye_evidence.answering.citations import CitationValidationError, citation_from_excerpt, validate_citations
from threadeye_evidence.retrieval.models import EvidenceCandidate, RankedEvidence, RetrievalFilters


def evidence(*, text: str = "A fictional supervisor records a traceable reason.") -> RankedEvidence:
    candidate = EvidenceCandidate(
        "a" * 24, "fixture.md", "b" * 64, "c" * 64, text, ("Synthetic", "Supervisor Review"),
        100, 100 + len(text), "threadeye-chunk-v1", "sanitized", "AUTH", "test", "model", "rev",
        "profile", "d" * 64, "corpus", "policy", "synthetic_test_fixture", 0.2, 0.2, 0.8,
    )
    return RankedEvidence(candidate, 1, ("keyword", "vector"), 1, 1, 2 / 61)


class CitationValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = evidence()
        self.excerpt = "A fictional supervisor records a traceable reason."
        self.citation = citation_from_excerpt(self.evidence, self.excerpt)
        self.filters = RetrievalFilters("corpus", "policy", "AUTH")
        self.config = SufficiencyConfig()

    def validate(self, citation=None, answer=None, evidence_rows=None, filters=None) -> None:
        validate_citations(
            "What reason does the supervisor record?",
            answer or self.excerpt,
            [citation or self.citation],
            evidence_rows or [self.evidence],
            filters or self.filters,
            "profile",
            self.config,
        )

    def test_valid_citation_verifies_all_provenance(self) -> None:
        report = validate_citations(
            "What reason does the supervisor record?", self.excerpt, [self.citation],
            [self.evidence], self.filters, "profile", self.config,
        )
        self.assertTrue(report.valid)
        self.assertEqual(report.validated_count, 1)

    def test_wrong_source_and_chunk_hashes_are_rejected(self) -> None:
        for citation in (
            replace(self.citation, source_sha256="e" * 64),
            replace(self.citation, chunk_sha256="f" * 64),
        ):
            with self.subTest(citation=citation), self.assertRaises(CitationValidationError):
                self.validate(citation=citation)

    def test_invalid_span_and_excerpt_mismatch_are_rejected(self) -> None:
        for citation in (
            replace(self.citation, normalized_end=self.evidence.candidate.normalized_end + 1),
            replace(self.citation, excerpt="forged excerpt"),
        ):
            with self.subTest(citation=citation), self.assertRaises(CitationValidationError):
                self.validate(citation=citation, answer=citation.excerpt)

    def test_spoofed_or_missing_chunk_is_rejected(self) -> None:
        with self.assertRaises(CitationValidationError):
            self.validate(citation=replace(self.citation, chunk_id="f" * 24))

    def test_wrong_authorization_policy_and_profile_are_rejected(self) -> None:
        with self.assertRaises(CitationValidationError):
            self.validate(filters=RetrievalFilters("corpus", "other-policy", "AUTH"))
        with self.assertRaises(CitationValidationError):
            validate_citations(
                "What reason does the supervisor record?", self.excerpt, [self.citation],
                [self.evidence], self.filters, "other-profile", self.config,
            )

    def test_answer_must_contain_exact_supporting_excerpt(self) -> None:
        with self.assertRaises(CitationValidationError):
            self.validate(answer="The system invented a different claim.")
        with self.assertRaises(CitationValidationError):
            self.validate(answer=self.excerpt + " An unsupported extra claim.")


if __name__ == "__main__":
    unittest.main()
