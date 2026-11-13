from __future__ import annotations

import unittest
import hashlib
from dataclasses import replace

from threadeye_evidence.answering.abstention import SufficiencyConfig
from threadeye_evidence.answering.citations import CitationValidationError, citation_from_excerpt, validate_citations
from threadeye_evidence.retrieval.models import EvidenceCandidate, RankedEvidence, RetrievalFilters


def evidence(*, text: str = "A fictional supervisor records a traceable reason.") -> RankedEvidence:
    candidate = EvidenceCandidate(
        "a" * 24, "fixture.md", "b" * 64, hashlib.sha256(text.encode()).hexdigest(), text, ("Synthetic", "Supervisor Review"),
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

    def test_tampered_stored_content_and_stale_span_are_rejected(self) -> None:
        tampered = replace(self.evidence.candidate, sanitized_text=self.excerpt + " altered")
        with self.assertRaises(CitationValidationError):
            self.validate(evidence_rows=[replace(self.evidence, candidate=tampered)])
        stale = replace(self.evidence.candidate, normalized_end=self.evidence.candidate.normalized_end + 1)
        with self.assertRaises(CitationValidationError):
            self.validate(evidence_rows=[replace(self.evidence, candidate=stale)])

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

    def test_every_optional_scope_filter_is_rechecked(self) -> None:
        candidate = self.evidence.candidate
        filters = (
            replace(self.filters, source_relative_path="other.md"),
            replace(self.filters, source_sha256="c" * 64),
            replace(self.filters, corpus_version="e" * 64),
            replace(self.filters, processing_version="stale"),
            replace(self.filters, document_classification="private"),
        )
        for active in filters:
            with self.subTest(active=active), self.assertRaises(CitationValidationError):
                self.validate(filters=active)

    def test_bounded_citation_count_and_unknown_private_path_fail(self) -> None:
        with self.assertRaises(CitationValidationError):
            validate_citations(
                "What reason does the supervisor record?", " ".join([self.excerpt] * 4),
                [self.citation] * 4, [self.evidence], self.filters, "profile", self.config,
            )
        forged = replace(self.citation, source_relative_path="private/nonexistent.md")
        with self.assertRaises(CitationValidationError):
            self.validate(citation=forged)

    def test_answer_must_contain_exact_supporting_excerpt(self) -> None:
        with self.assertRaises(CitationValidationError):
            self.validate(answer="The system invented a different claim.")
        with self.assertRaises(CitationValidationError):
            self.validate(answer=self.excerpt + " An unsupported extra claim.")

    def test_heading_overlap_cannot_make_unrelated_excerpt_relevant(self) -> None:
        unrelated = evidence(text="This document is synthetic.")
        unrelated = replace(unrelated, candidate=replace(
            unrelated.candidate,
            heading_hierarchy=("Fictional Mill Evidence Packet",),
            cosine_similarity=0.91,
        ))
        citation = citation_from_excerpt(unrelated, "This document is synthetic.")
        with self.assertRaises(CitationValidationError):
            validate_citations(
                "What spindle speed does the fictional weaving machine use?",
                citation.excerpt,
                [citation],
                [unrelated],
                self.filters,
                "profile",
                self.config,
            )


if __name__ == "__main__":
    unittest.main()
