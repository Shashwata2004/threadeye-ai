from __future__ import annotations

import math
import unittest

from threadeye_evidence.vector.embeddings import (
    EmbeddingMetadata,
    EmbeddingValidationError,
    MockEmbeddingProvider,
    validate_vectors,
)


class EmbeddingTests(unittest.TestCase):
    def test_metadata_has_stable_profile_key(self) -> None:
        first = EmbeddingMetadata("provider", "model", "revision", 8)
        second = EmbeddingMetadata("provider", "model", "revision", 8)
        changed = EmbeddingMetadata("provider", "model", "revision-2", 8)
        self.assertEqual(first.profile_key, second.profile_key)
        self.assertNotEqual(first.profile_key, changed.profile_key)

    def test_metadata_rejects_invalid_metric_and_dimension(self) -> None:
        with self.assertRaises(EmbeddingValidationError):
            EmbeddingMetadata("provider", "model", "revision", 0)
        with self.assertRaises(EmbeddingValidationError):
            EmbeddingMetadata("provider", "model", "revision", 8, "euclidean")

    def test_mock_provider_is_repeatable_and_batched(self) -> None:
        provider = MockEmbeddingProvider(12)
        first = provider.embed_documents(["alpha", "beta"], batch_size=2)
        second = provider.embed_documents(["alpha", "beta"], batch_size=1)
        self.assertEqual(first, second)
        self.assertEqual([len(vector) for vector in first], [12, 12])
        self.assertTrue(all(math.isclose(sum(value * value for value in vector), 1.0) for vector in first))

    def test_empty_or_invalid_inputs_are_rejected(self) -> None:
        provider = MockEmbeddingProvider()
        for invalid in ([], [""], ["   "]):
            with self.assertRaises(EmbeddingValidationError):
                provider.embed_documents(invalid)
        with self.assertRaises(EmbeddingValidationError):
            provider.embed_documents(["valid"], batch_size=0)

    def test_nan_infinity_and_dimension_mismatch_are_rejected(self) -> None:
        for vector in ([0.0, math.nan], [0.0, math.inf], [0.0]):
            with self.assertRaises(EmbeddingValidationError):
                validate_vectors([vector], count=1, dimensions=2)

    def test_query_embedding_uses_the_same_profile_dimension(self) -> None:
        provider = MockEmbeddingProvider(9)
        self.assertEqual(len(provider.embed_query("synthetic query")), 9)
