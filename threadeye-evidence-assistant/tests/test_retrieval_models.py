from __future__ import annotations

import unittest

from threadeye_evidence.retrieval.models import (
    MAX_QUERY_CHARS,
    RetrievalFilters,
    RetrievalValidationError,
    validate_limit,
    validate_query,
)
from threadeye_evidence.retrieval.policy import RetrievalAccessPolicy


class RetrievalContractTests(unittest.TestCase):
    def test_query_is_trimmed_and_bounded(self) -> None:
        self.assertEqual(validate_query("  fabric receiving  "), "fabric receiving")
        with self.assertRaises(RetrievalValidationError):
            validate_query(" ")
        with self.assertRaises(RetrievalValidationError):
            validate_query("x" * (MAX_QUERY_CHARS + 1))

    def test_top_k_rejects_bool_zero_and_excessive_values(self) -> None:
        for value in (True, 0, 21):
            with self.subTest(value=value), self.assertRaises(RetrievalValidationError):
                validate_limit(value)

    def test_required_authorization_filters_fail_closed(self) -> None:
        for values in (("", "policy", "ref"), ("corpus", "", "ref"), ("corpus", "policy", "")):
            with self.subTest(values=values), self.assertRaises(RetrievalValidationError):
                RetrievalFilters(*values)

    def test_optional_filters_are_validated(self) -> None:
        with self.assertRaises(ValueError):
            RetrievalFilters("c", "p", "r", source_relative_path="../secret.md")
        with self.assertRaises(RetrievalValidationError):
            RetrievalFilters("c", "p", "r", source_sha256="bad")
        with self.assertRaises(RetrievalValidationError):
            RetrievalFilters("c", "p", "r", corpus_version="A" * 64)

    def test_filter_serialization_omits_absent_values(self) -> None:
        payload = RetrievalFilters("c", "p", "r", source_relative_path="fixture.md").to_mapping()
        self.assertEqual(payload, {"corpus_id": "c", "access_policy": "p", "authorization_reference": "r", "source_relative_path": "fixture.md"})

    def test_serving_authorization_is_independent_and_explicit(self) -> None:
        with self.assertRaises(ValueError):
            RetrievalAccessPolicy("unassigned", "policy", "synthetic", True)
        denied = RetrievalAccessPolicy("unassigned", "deny", "unclassified", False)
        self.assertFalse(denied.authorized)


if __name__ == "__main__":
    unittest.main()
