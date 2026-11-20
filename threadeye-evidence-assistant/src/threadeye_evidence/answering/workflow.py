"""Opt-in LangGraph orchestration with one explicitly disclosed recovery attempt."""

from __future__ import annotations

from dataclasses import replace
from importlib.metadata import version
from time import perf_counter
from typing import Any, TypedDict

from threadeye_evidence.answering.engine import EvidenceAnswerEngine
from threadeye_evidence.answering.models import AnswerStatus, EvidenceAnswer
from threadeye_evidence.retrieval.models import RetrievalMode


class WorkflowState(TypedDict):
    question: str
    options: dict[str, Any]
    response: EvidenceAnswer
    attempts: list[dict[str, Any]]


class EvidenceRecoveryWorkflow:
    """A read-only workflow, not a generative LLM or autonomous QC authority.

    Each attempt passes through the original authorization, policy, sufficiency
    and citation checks. Only an identified vector retrieval failure can trigger
    one keyword-only attempt. Weak evidence and denied requests never trigger it.
    """

    def __init__(self, engine: EvidenceAnswerEngine) -> None:
        try:
            from langgraph.graph import END, START, StateGraph
        except ImportError as exc:
            raise RuntimeError(
                "LangGraph mode requires Python >=3.10 and the agentic extra: "
                "pip install -e './threadeye-evidence-assistant[agentic]'"
            ) from exc
        self.engine = engine
        graph = StateGraph(WorkflowState)
        graph.add_node("primary_answer", self._primary)
        graph.add_node("keyword_recovery", self._recover)
        graph.add_node("finalize", self._finalize)
        graph.add_edge(START, "primary_answer")
        graph.add_conditional_edges(
            "primary_answer", self._route,
            {"recover": "keyword_recovery", "finish": "finalize"},
        )
        graph.add_edge("keyword_recovery", "finalize")
        graph.add_edge("finalize", END)
        self.graph = graph.compile()

    @staticmethod
    def _attempt(response: EvidenceAnswer, node: str) -> dict[str, Any]:
        return {
            "node": node,
            "mode": response.retrieval_mode,
            "status": response.status,
            "reason": response.abstention_reason,
            "failure_stage": response.retrieval_metadata.get("failure_stage"),
        }

    def _primary(self, state: WorkflowState) -> dict[str, Any]:
        response = self.engine.answer(state["question"], **state["options"])
        return {"response": response, "attempts": [self._attempt(response, "primary_answer")]}

    @staticmethod
    def _route(state: WorkflowState) -> str:
        response = state["response"]
        if (
            response.status == AnswerStatus.RETRIEVAL_ERROR.value
            and response.retrieval_metadata.get("failure_stage") == "vector_retrieval"
            and response.retrieval_mode in {"vector", "hybrid"}
        ):
            return "recover"
        return "finish"

    def _recover(self, state: WorkflowState) -> dict[str, Any]:
        options = {**state["options"], "mode": RetrievalMode.KEYWORD}
        response = self.engine.answer(state["question"], **options)
        return {
            "response": response,
            "attempts": [*state["attempts"], self._attempt(response, "keyword_recovery")],
        }

    @staticmethod
    def _finalize(state: WorkflowState) -> dict[str, Any]:
        response = state["response"]
        recovered = len(state["attempts"]) > 1
        metadata = {
            **response.retrieval_metadata,
            "orchestration": {
                "framework": "langgraph", "version": version("langgraph"),
                "workflow": "evidence-recovery-v1", "attempts": state["attempts"],
                "max_attempts": 2, "generative_llm": False,
            },
        }
        if recovered:
            metadata["degraded"] = True
            metadata["degradation_reason"] = "vector_retrieval_failed_keyword_only_attempt"
        limitations = response.limitations
        if recovered:
            limitations += ("Vector retrieval failed; the final attempt used keyword-only retrieval.",)
        return {"response": replace(response, retrieval_metadata=metadata, limitations=limitations)}

    def answer(self, question: str, **options: Any) -> EvidenceAnswer:
        started = perf_counter()
        result = self.graph.invoke(
            {"question": question, "options": options, "attempts": []},
            config={"recursion_limit": 8},
        )
        return replace(result["response"], latency_ms=(perf_counter() - started) * 1_000)
