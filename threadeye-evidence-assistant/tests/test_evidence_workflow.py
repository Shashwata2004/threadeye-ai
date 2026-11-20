"""Exercise real LangGraph execution around the existing evidence engine."""

import unittest

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.answering.workflow import EvidenceRecoveryWorkflow
from threadeye_evidence.retrieval.engine import RetrievalBackendError
from threadeye_evidence.retrieval.models import RetrievalMode

from test_answering_engine import FILTERS, FakeRetriever, ranked


QUESTION = "What reason does the supervisor record?"


class RecordingRetriever(FakeRetriever):
    def __init__(self, *, fail_vector=False, fail_keyword=False, **kwargs):
        super().__init__(**kwargs)
        self.fail_vector = fail_vector
        self.fail_keyword = fail_keyword
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append(kwargs.copy())
        mode = RetrievalMode(kwargs["mode"])
        if self.fail_vector and mode in {RetrievalMode.HYBRID, RetrievalMode.VECTOR}:
            raise RetrievalBackendError("vector retrieval failed")
        if self.fail_keyword and mode is RetrievalMode.KEYWORD:
            raise RetrievalBackendError("keyword retrieval failed")
        return super().search(query, **kwargs)


class EvidenceWorkflowTests(unittest.TestCase):
    def workflow(self, retriever):
        return EvidenceRecoveryWorkflow(EvidenceAnswerEngine(retriever))

    def test_success_keeps_citations_and_records_single_attempt(self):
        retriever = RecordingRetriever()
        result = self.workflow(retriever).answer(QUESTION, filters=FILTERS)
        self.assertEqual(result.status, "answered")
        self.assertEqual(len(result.citations), 1)
        trace = result.retrieval_metadata["orchestration"]
        self.assertEqual(trace["framework"], "langgraph")
        self.assertFalse(trace["generative_llm"])
        self.assertEqual(len(trace["attempts"]), 1)

    def test_vector_failure_routes_once_to_authorized_keyword_recovery(self):
        retriever = RecordingRetriever(fail_vector=True)
        result = self.workflow(retriever).answer(QUESTION, filters=FILTERS, top_k=2, candidate_k=4)
        self.assertEqual(result.status, "answered")
        self.assertEqual(result.retrieval_mode, "keyword")
        self.assertTrue(result.retrieval_metadata["degraded"])
        self.assertEqual(len(retriever.calls), 2)
        self.assertIs(retriever.calls[1]["filters"], FILTERS)
        self.assertEqual(retriever.calls[1]["top_k"], 2)
        self.assertEqual(retriever.calls[1]["candidate_k"], 4)
        self.assertEqual(len(result.citations), 1)
        self.assertEqual(result.retrieval_metadata["orchestration"]["attempts"][0]["failure_stage"], "vector_retrieval")

    def test_failed_recovery_stops_at_two_attempts(self):
        retriever = RecordingRetriever(fail_vector=True, fail_keyword=True)
        result = self.workflow(retriever).answer(QUESTION, filters=FILTERS)
        self.assertEqual(result.status, "retrieval_error")
        self.assertIsNone(result.answer)
        self.assertEqual(len(retriever.calls), 2)

    def test_authorization_and_policy_rejections_do_not_search_or_retry(self):
        for count, question, status in (
            (0, QUESTION, "unauthorized"),
            (1, "Approve this real roll for shipment.", "unsupported_request"),
            (1, " ", "validation_error"),
        ):
            with self.subTest(status=status):
                retriever = RecordingRetriever(count=count, fail_vector=True)
                result = self.workflow(retriever).answer(question, filters=FILTERS)
                self.assertEqual(result.status, status)
                self.assertEqual(retriever.calls, [])

    def test_weak_evidence_does_not_trigger_another_attempt(self):
        retriever = RecordingRetriever(rows=[ranked("A fictional unrelated paragraph.")])
        result = self.workflow(retriever).answer("What is the lunar temperature?", filters=FILTERS)
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertEqual(len(retriever.calls), 1)

    def test_recovery_rechecks_authorization(self):
        retriever = RecordingRetriever(fail_vector=True)
        original = retriever.search

        def revoke(query, **kwargs):
            retriever.store.count = 0
            return original(query, **kwargs)

        retriever.search = revoke
        result = self.workflow(retriever).answer(QUESTION, filters=FILTERS)
        self.assertEqual(result.status, "unauthorized")
        self.assertEqual(len(retriever.calls), 1)
        self.assertIsNone(result.answer)

    def test_keyword_mode_does_not_retry_itself(self):
        retriever = RecordingRetriever(fail_keyword=True)
        result = self.workflow(retriever).answer(QUESTION, filters=FILTERS, mode="keyword")
        self.assertEqual(result.status, "retrieval_error")
        self.assertEqual(len(retriever.calls), 1)

    def test_recovery_cannot_bypass_citation_validation(self):
        retriever = RecordingRetriever(fail_vector=True)
        engine = EvidenceAnswerEngine(retriever)

        def invalid(*args):
            raise ValueError("invalid citation fixture")

        engine.provider.build = invalid
        result = EvidenceRecoveryWorkflow(engine).answer(QUESTION, filters=FILTERS)
        self.assertEqual(result.status, "citation_validation_failed")
        self.assertIsNone(result.answer)
        self.assertEqual(result.citations, ())


if __name__ == "__main__":
    unittest.main()
