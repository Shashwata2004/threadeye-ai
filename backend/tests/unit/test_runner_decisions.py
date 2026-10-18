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


def test_a_missed_defect_drawn_on_the_video_takes_its_position_and_size_from_the_box() -> None:
    from threadeye.core.geometry import view_to_roll

    r = make_runner()
    r.advance(150)
    box = (300.0, 200.0, 420.0, 260.0)  # view pixels of frame 150
    events = r.decide(None, {"action": "manual", "cls": "hole", "frame": 150, "bbox_px": box}, key("m"))
    view = next(e.payload["defect"] for e in events if e.payload.get("decision"))
    expected = view_to_roll(box, r.track[150], r.calibration)
    assert view["origin"] == "manual" and view["status"] == "confirmed"
    assert view["center_yd"] == pytest.approx(expected.center_yd, abs=1e-4)
    assert view["across_start_cm"] == pytest.approx(expected.across_start_cm, abs=0.01)
    assert view["length_in"] == pytest.approx(expected.length_in, abs=1e-3)
    assert view["length_source"] == "pixels" and view["best_bbox_px"] == list(box)
    assert view["best_frame"] == 150 and "drawn on the video" in view["explanation"]

    # A box outside the camera view, or too small, is refused.
    for bad in [(-50.0, -50.0, -10.0, -10.0), (10.0, 10.0, 11.0, 11.0)]:
        with pytest.raises(DecisionError):
            r.decide(None, {"action": "manual", "cls": "hole", "frame": 150, "bbox_px": bad}, key("n"))
    with pytest.raises(DecisionError):  # neither a box nor a yard and a length
        r.decide(None, {"action": "manual", "cls": "hole"}, key("o"))


def test_confirm_all_pending_is_one_decision_per_defect_and_replays() -> None:
    r = make_runner()
    events = r.run_to_end()
    hole = by_cls(r, "hole")
    events += r.decide(hole, {"action": "reject", "reason_category": "other"}, key("a"))
    assert r.pending_defects() == sorted(r.pending_defects(), key=lambda no: r.views()[no]["center_yd"])
    first = r.views()[r.pending_defects()[0]]["center_yd"]
    assert r.pending_defects(up_to_yd=first) == r.pending_defects()[:1]

    pending = r.pending_defects()
    bulk = r.decide_many(pending, {"action": "confirm", "bulk": True}, key("b"))
    decided = [e for e in bulk if e.payload.get("decision")]
    assert sorted(e.payload["defect"]["defect_no"] for e in decided) == sorted(pending)
    assert all(e.payload["defect"]["status"] == "confirmed" for e in decided)
    assert len({e.idempotency_key for e in bulk}) == len(bulk)
    assert r.pending_defects() == [] and r.views()[hole]["status"] == "rejected"

    rebuilt = replay(events + bulk, r.checkpoint)
    assert rebuilt.views() == r.views() and rebuilt.score_payload() == r.score_payload()

    nondefect = next(no for no, v in r.views().items() if v["kind"] == "nondefect")
    with pytest.raises(DecisionError):  # all or nothing: a non-defect in the list refuses the whole call
        r.decide_many([hole, nondefect], {"action": "confirm"}, key("c"))
    assert r.views()[hole]["status"] == "rejected"


def test_the_verdict_is_settled_when_pending_defects_cannot_change_it() -> None:
    # Micro roll (simulator parity): 1 point = 20.32 per 100 sq yd, limit 40 → 2 points already fail.
    r = make_runner()
    r.run_to_end()
    assert not r.verdict_settled()  # all pending: 0 points (PASS) … 7 points (FAIL)
    r.decide(by_cls(r, "slub"), {"action": "confirm"}, key("a"))  # 3 points: FAIL whatever the rest are
    assert r.verdict_settled() and r.score_payload()["verdict_settled"] is True
    assert r.score_payload()["pending"] == 2

    r2 = make_runner()
    r2.run_to_end()
    for no in r2.pending_defects():
        r2.decide(no, {"action": "reject", "reason_category": "other"}, key(no))
    assert r2.verdict_settled()  # nothing pending: trivially settled
