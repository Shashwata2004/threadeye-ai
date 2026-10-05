"""Inspector decisions in the runner, and rebuilding a runner from its events (restart / power cut)."""

from __future__ import annotations

import pytest

from tests.unit.test_runner_and_eval import make_runner
from threadeye.core.runner import DecisionError, Runner, RunnerEvent
from threadeye.providers.simulated import REALISTIC


def key(prefix: str):  # type: ignore[no-untyped-def]
    return lambda type_, no: f"{prefix}:{type_}:{no}"


def by_cls(r: Runner, cls: str) -> str:
    return next(v["defect_no"] for v in r.views().values() if v["current_cls"] == cls and v["kind"] == "defect")


def replay(events: list[RunnerEvent], checkpoint: int, config=None) -> Runner:  # type: ignore[no-untyped-def]
    fresh = make_runner(config) if config else make_runner()
    fresh.restore(((e.type, e.payload) for e in events), checkpoint)
    return fresh


def test_decisions_change_status_class_length_and_score() -> None:
    r = make_runner()
    r.run_to_end()
    hole, stain = by_cls(r, "hole"), by_cls(r, "stain")
    assert r.score_payload()["pending"] == 3 and r.score_payload()["confirmed_points"] == 0

    ev = r.decide(hole, {"action": "reject", "reason_category": "pin_hole"}, key("a"))
    target = [e for e in ev if e.payload.get("decision")]
    assert len(target) == 1 and target[0].payload["defect"]["status"] == "rejected"
    assert ev[-1].type == "score.updated" and ev[-1].payload["provisional_points"] == 5

    r.decide(stain, {"action": "length", "length_in": 10.0}, key("b"))
    assert r.views()[stain]["length_source"] == "inspector" and r.views()[stain]["points"] == 4

    r.decide(stain, {"action": "reclassify", "to_cls": "oil"}, key("c"))  # aliases resolve
    assert r.views()[stain]["current_cls"] == "oil_stain" and r.views()[stain]["status"] == "confirmed"

    with pytest.raises(DecisionError):
        r.decide(stain, {"action": "reclassify", "to_cls": "sticker"}, key("d"))
    nondefect = next(no for no, v in r.views().items() if v["kind"] == "nondefect")
    with pytest.raises(DecisionError):
        r.decide(nondefect, {"action": "confirm"}, key("e"))
    r.decide(nondefect, {"action": "promote"}, key("f"))
    assert r.views()[nondefect]["kind"] == "defect" and r.views()[nondefect]["current_cls"] == "other_defect"

    added = r.decide(None, {"action": "manual", "cls": "knot", "center_yd": 1.2, "length_in": 0.5}, key("g"))
    manual = next(e.payload["defect"] for e in added if e.payload.get("decision"))
    assert manual["defect_no"] == "M-01" and manual["origin"] == "manual" and manual["points"] == 1


@pytest.mark.parametrize("config", [None, REALISTIC])
def test_a_runner_rebuilt_from_its_events_is_identical(config) -> None:  # type: ignore[no-untyped-def]
    r = make_runner(config) if config else make_runner()
    events: list[RunnerEvent] = []
    events += r.advance(90)
    first = sorted(no for no, v in r.views().items() if v["kind"] == "defect")[0]
    events += r.decide(first, {"action": "confirm"}, key("x"))
    events += r.advance(204)
    events += r.decide(None, {"action": "manual", "cls": "hole", "center_yd": 2.9, "length_in": 2.0}, key("y"))
    if len(r.defect_numbers()) > 2:
        events += r.decide(r.defect_numbers()[1], {"action": "reject", "reason_category": "other"}, key("z"))

    rebuilt = replay(events, r.checkpoint, config)
    assert rebuilt.views() == r.views()
    assert rebuilt.score_payload() == r.score_payload()
    # Nothing is emitted for defects that did not change, so a rebuilt runner continues seamlessly.
    assert rebuilt.advance(204) == [] and rebuilt.finished


def test_defect_events_are_emitted_only_on_change() -> None:
    r = make_runner()
    first = r.advance(60)
    upserts = [e for e in first if e.type == "defect.upserted"]
    assert upserts and all(e.payload["change"] == "detected" for e in upserts)
    later = r.advance(61)
    assert not [e for e in later if e.type == "defect.upserted"]
