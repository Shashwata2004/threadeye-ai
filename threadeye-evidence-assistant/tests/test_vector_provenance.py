from __future__ import annotations

import dataclasses
import unittest

from threadeye_evidence.vector.provenance import ProvenanceValidationError, approved_chunk_batch

from vector_helpers import synthetic_result


class VectorProvenanceTests(unittest.TestCase):
    def test_approved_ingestion_result_is_accepted(self) -> None:
        result = synthetic_result()
        batch = approved_chunk_batch(result)
        self.assertEqual(batch.source_sha256, result.source_sha256)
        self.assertEqual(batch.chunks, result.chunks)

    def test_chunk_hash_mismatch_is_rejected(self) -> None:
        result = synthetic_result()
        altered = dataclasses.replace(result.chunks[0], chunk_sha256="0" * 64)
        tampered = dataclasses.replace(result, chunks=(altered, *result.chunks[1:]))
        with self.assertRaisesRegex(ProvenanceValidationError, "hash mismatch"):
            approved_chunk_batch(tampered)

    def test_duplicate_chunk_is_rejected(self) -> None:
        result = synthetic_result()
        tampered = dataclasses.replace(result, chunks=(result.chunks[0], result.chunks[0]))
        with self.assertRaises(ProvenanceValidationError):
            approved_chunk_batch(tampered)

    def test_authorization_mismatch_is_rejected(self) -> None:
        result = synthetic_result()
        altered = dataclasses.replace(result.chunks[0], approval_reference="OTHER")
        tampered = dataclasses.replace(result, chunks=(altered, *result.chunks[1:]))
        with self.assertRaisesRegex(ProvenanceValidationError, "provenance"):
            approved_chunk_batch(tampered)

    def test_unsanitized_secret_is_rejected(self) -> None:
        result = synthetic_result()
        content = result.chunks[0].content + "\napi_key=sk-abcdefghijklmnopqrstuvwxyz123456\n"
        altered = dataclasses.replace(
            result.chunks[0],
            content=content,
            chunk_sha256=__import__("hashlib").sha256(content.encode()).hexdigest(),
            normalized_end=result.chunks[0].normalized_start + len(content),
        )
        tampered = dataclasses.replace(result, chunks=(altered, *result.chunks[1:]))
        with self.assertRaises(ProvenanceValidationError):
            approved_chunk_batch(tampered)
