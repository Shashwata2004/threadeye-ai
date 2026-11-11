from __future__ import annotations

import unittest

from threadeye_evidence.vector.embeddings import MockEmbeddingProvider
from threadeye_evidence.vector.indexing import corpus_version

from vector_helpers import synthetic_result


class VectorIndexingTests(unittest.TestCase):
    def test_corpus_version_is_repeatable(self) -> None:
        result = synthetic_result()
        provider = MockEmbeddingProvider(384)
        self.assertEqual(corpus_version(result, provider), corpus_version(result, provider))

    def test_model_revision_changes_corpus_version(self) -> None:
        result = synthetic_result()
        first = MockEmbeddingProvider(384, revision="one")
        second = MockEmbeddingProvider(384, revision="two")
        self.assertNotEqual(corpus_version(result, first), corpus_version(result, second))

    def test_source_content_change_changes_corpus_version(self) -> None:
        first = synthetic_result("# Synthetic\n\nFirst fictional version.\n")
        second = synthetic_result("# Synthetic\n\nSecond fictional version.\n")
        provider = MockEmbeddingProvider(384)
        self.assertNotEqual(corpus_version(first, provider), corpus_version(second, provider))
