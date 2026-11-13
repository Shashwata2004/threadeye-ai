from __future__ import annotations

import hashlib
import unittest

from threadeye_evidence.corpus.chunking import ChunkConfig, chunk_markdown


def chunks_for(text: str, *, target: int = 120, maximum: int = 180):
    return chunk_markdown(
        text,
        source_relative_path="synthetic.md",
        source_sha256="a" * 64,
        sanitization_status="clean",
        approval_reference="TEST-AUTH",
        config=ChunkConfig(target_chars=target, max_chars=maximum),
    )


class ChunkingTests(unittest.TestCase):
    def test_heading_hierarchy_is_preserved_and_code_headings_are_ignored(self) -> None:
        text = "# Parent\n\nIntro.\n\n## Child\n\n```md\n# not a heading\n```\n\nChild text.\n"
        chunks = chunks_for(text, target=200, maximum=300)
        self.assertEqual(chunks[0].heading_path, ("Parent",))
        self.assertEqual(chunks[1].heading_path, ("Parent", "Child"))
        self.assertEqual("".join(chunk.content for chunk in chunks), text)

    def test_short_sections_produce_variable_sized_chunks(self) -> None:
        text = "# A\n\nShort.\n\n# B\n\nThis section contains a substantially longer but still coherent paragraph.\n"
        chunks = chunks_for(text, target=150, maximum=300)
        self.assertEqual(len(chunks), 2)
        self.assertNotEqual(chunks[0].size_chars, chunks[1].size_chars)

    def test_oversized_section_splits_at_bounded_semantic_boundaries(self) -> None:
        paragraphs = [f"Paragraph {index} contains enough synthetic words to exercise semantic splitting." for index in range(8)]
        text = "# Long\n\n" + "\n\n".join(paragraphs) + "\n"
        chunks = chunks_for(text, target=140, maximum=190)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(chunk.size_chars <= 190 for chunk in chunks))
        self.assertEqual("".join(chunk.content for chunk in chunks), text)

    def test_chunk_ids_and_hashes_are_stable(self) -> None:
        text = "# Stable\n\nOne paragraph.\n"
        first = chunks_for(text, target=100, maximum=150)
        second = chunks_for(text, target=100, maximum=150)
        self.assertEqual(first, second)
        self.assertEqual(first[0].chunk_sha256, hashlib.sha256(first[0].content.encode()).hexdigest())
        self.assertEqual(len(first[0].chunk_id), 24)

    def test_provenance_spans_are_contiguous_and_complete(self) -> None:
        text = "# One\n\n" + ("Sentence one. Sentence two.\n\n" * 10) + "## Two\n\nEnd.\n"
        chunks = chunks_for(text, target=110, maximum=160)
        self.assertEqual(chunks[0].normalized_start, 0)
        self.assertEqual(chunks[-1].normalized_end, len(text))
        for index, chunk in enumerate(chunks):
            self.assertEqual(chunk.position, index)
            self.assertEqual(text[chunk.normalized_start : chunk.normalized_end], chunk.content)
            if index:
                self.assertEqual(chunks[index - 1].normalized_end, chunk.normalized_start)
            self.assertEqual(chunk.source_span_basis, "sanitized_normalized_text_v1")
            self.assertEqual(chunk.approval_reference, "TEST-AUTH")
            self.assertEqual(chunk.overlap_chars, 0)


if __name__ == "__main__":
    unittest.main()
