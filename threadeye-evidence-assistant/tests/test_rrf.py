from __future__ import annotations

import math
import unittest
from dataclasses import replace

from threadeye_evidence.retrieval.fusion import RRFConfig, fuse_rrf, rank_single
from threadeye_evidence.retrieval.models import EvidenceCandidate, RetrievalValidationError


def candidate(chunk_id: str, *, keyword: float | None = None, similarity: float | None = None) -> EvidenceCandidate:
    return EvidenceCandidate(
        chunk_id, "fixture.md", "a" * 64, "b" * 64, "sanitized", ("Synthetic",), 0, 9,
        "heading-chunker-v1", "sanitized", "AUTH", "test", "model", "revision", "profile",
        "c" * 64, "corpus", "test-policy", "synthetic_test_fixture", keyword,
        None if similarity is None else 1.0 - similarity, similarity,
    )


class ReciprocalRankFusionTests(unittest.TestCase):
    def test_formula_uses_one_based_ranks(self) -> None:
        result = fuse_rrf([candidate("a", keyword=0.8)], [candidate("a", similarity=0.9)], top_k=1, config=RRFConfig())
        self.assertTrue(math.isclose(result[0].rrf_score, 2.0 / 61.0))
        self.assertEqual((result[0].keyword_rank, result[0].vector_rank), (1, 1))

    def test_deduplicates_and_preserves_both_native_scores(self) -> None:
        result = fuse_rrf([candidate("a", keyword=0.7)], [candidate("a", similarity=0.6)], top_k=1, config=RRFConfig())[0]
        self.assertEqual(result.retrieval_methods, ("keyword", "vector"))
        self.assertEqual(result.candidate.keyword_score, 0.7)
        self.assertEqual(result.candidate.cosine_similarity, 0.6)

    def test_weights_change_order_without_combining_native_scores(self) -> None:
        keyword = [candidate("lex", keyword=0.9)]
        vector = [candidate("sem", similarity=0.9)]
        result = fuse_rrf(keyword, vector, top_k=2, config=RRFConfig(keyword_weight=2, vector_weight=1))
        self.assertEqual([item.candidate.chunk_id for item in result], ["lex", "sem"])

    def test_missing_branch_result_contributes_only_existing_rank(self) -> None:
        result = fuse_rrf([candidate("lex")], [], top_k=1, config=RRFConfig())[0]
        self.assertEqual(result.rrf_score, 1.0 / 61.0)
        self.assertIsNone(result.vector_rank)

    def test_ties_are_broken_by_stable_chunk_id(self) -> None:
        result = fuse_rrf([candidate("b")], [candidate("a")], top_k=2, config=RRFConfig())
        self.assertEqual([item.candidate.chunk_id for item in result], ["a", "b"])

    def test_top_k_is_strict_and_reproducible(self) -> None:
        inputs = [candidate(str(i)) for i in range(5)]
        first = fuse_rrf(inputs, list(reversed(inputs)), top_k=3, config=RRFConfig())
        second = fuse_rrf(inputs, list(reversed(inputs)), top_k=3, config=RRFConfig())
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)

    def test_conflicting_provenance_fails_closed(self) -> None:
        with self.assertRaises(RetrievalValidationError):
            fuse_rrf([candidate("a")], [replace(candidate("a"), source_sha256="d" * 64)], top_k=1, config=RRFConfig())

    def test_invalid_rrf_parameters_are_rejected(self) -> None:
        for config in ((0, 1, 1), (60, 0, 1), (60, 1, float("nan"))):
            with self.subTest(config=config), self.assertRaises(RetrievalValidationError):
                RRFConfig(*config)

    def test_single_mode_records_only_its_own_rank(self) -> None:
        ranked = rank_single([candidate("a")], mode="vector", top_k=1)[0]
        self.assertEqual(ranked.vector_rank, 1)
        self.assertIsNone(ranked.keyword_rank)
        self.assertIsNone(ranked.rrf_score)


if __name__ == "__main__":
    unittest.main()
