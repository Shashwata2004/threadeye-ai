"""Detection quality metrics against an answer key (brief §8, PLAN.md §8 benchmark).

Precision, recall, F1, recall per class, class accuracy, and every false positive explained by the
non-defect that caused it (sticker / loose thread / wrinkle / selvage / board / unexplained).

Matching: a prediction and a true defect match when roll-box IoU > 0.3 or centres are within 3 cm,
assigned greedily one-to-one (best IoU first). Must agree with ``tools/simulator/evaluate.py``; a parity
test runs as soon as that file is in the repo.

Pure: the caller converts the answer key to the plain types below. Only predictions of kind "defect"
count; non-defects the filter set aside are reported separately as correctly ignored or not.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from threadeye.core.geometry import RollBox


@dataclass(frozen=True)
class TruthDefect:
    defect_id: str
    cls: str
    box: RollBox
    points: int


@dataclass(frozen=True)
class TruthNuisance:
    type: str
    box: RollBox


@dataclass(frozen=True)
class Prediction:
    pred_id: str
    cls: str
    box: RollBox
    is_defect: bool
    nondefect_category: str | None = None


@dataclass
class EvalResult:
    tp: int
    fp: int
    fn: int
    precision: float
    recall: float
    f1: float
    class_accuracy: float | None
    recall_per_class: dict[str, float]
    matches: list[tuple[str, str, float]]
    """(pred_id, defect_id, iou)"""
    false_positives: list[tuple[str, str]]
    """(pred_id, explained_by)"""
    missed: list[str]
    fp_by_type: dict[str, int] = field(default_factory=dict)
    nondefects_ignored: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "tp": self.tp,
            "fp": self.fp,
            "fn": self.fn,
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "class_accuracy": None if self.class_accuracy is None else round(self.class_accuracy, 4),
            "recall_per_class": {k: round(v, 4) for k, v in sorted(self.recall_per_class.items())},
            "fp_by_type": dict(sorted(self.fp_by_type.items())),
            "nondefects_ignored": dict(sorted(self.nondefects_ignored.items())),
            "missed": self.missed,
        }


def _matches(a: RollBox, b: RollBox, iou_threshold: float, center_cm: float) -> float | None:
    iou = a.iou(b)
    if iou > iou_threshold:
        return iou
    if a.center_distance_cm(b) <= center_cm:
        return max(iou, 1e-6)
    return None


def _explain(box: RollBox, nuisances: list[TruthNuisance], fabric_width_cm: float, selvage_band_cm: float) -> str:
    for n in nuisances:
        if box.intersection_area(n.box) > 0 or box.center_distance_cm(n.box) <= max(n.box.width_cm, 1.0):
            return n.type
    if box.across_end_cm <= 0 or box.across_start_cm >= fabric_width_cm:
        return "board"
    center = (box.across_start_cm + box.across_end_cm) / 2  # the app's rule (NonDefectFilter.in_selvage)
    if selvage_band_cm > 0 and (center <= selvage_band_cm or center >= fabric_width_cm - selvage_band_cm):
        return "selvage"
    return "unexplained"


def evaluate(
    predictions: list[Prediction],
    truths: list[TruthDefect],
    nuisances: list[TruthNuisance],
    *,
    fabric_width_cm: float,
    selvage_band_cm: float = 0.0,
    iou_threshold: float = 0.3,
    center_cm: float = 3.0,
) -> EvalResult:
    preds = [p for p in predictions if p.is_defect]
    candidates = []
    for p in preds:
        for t in truths:
            score = _matches(p.box, t.box, iou_threshold, center_cm)
            if score is not None:
                candidates.append((score, -p.box.center_distance_cm(t.box), p, t))
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)

    used_p: set[str] = set()
    used_t: set[str] = set()
    matches: list[tuple[str, str, float]] = []
    correct_class = 0
    for score, _neg_dist, p, t in candidates:
        if p.pred_id in used_p or t.defect_id in used_t:
            continue
        used_p.add(p.pred_id)
        used_t.add(t.defect_id)
        matches.append((p.pred_id, t.defect_id, round(score, 4)))
        correct_class += p.cls == t.cls

    false_positives = [
        (p.pred_id, _explain(p.box, nuisances, fabric_width_cm, selvage_band_cm))
        for p in preds
        if p.pred_id not in used_p
    ]
    missed = [t.defect_id for t in truths if t.defect_id not in used_t]

    tp, fp, fn = len(matches), len(false_positives), len(missed)
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    per_class_total = Counter(t.cls for t in truths)
    per_class_hit = Counter(t.cls for t in truths if t.defect_id in used_t)
    ignored = Counter(p.nondefect_category or "unknown" for p in predictions if not p.is_defect)

    return EvalResult(
        tp=tp,
        fp=fp,
        fn=fn,
        precision=precision,
        recall=recall,
        f1=f1,
        class_accuracy=correct_class / tp if tp else None,
        recall_per_class={c: per_class_hit[c] / n for c, n in per_class_total.items()},
        matches=matches,
        false_positives=false_positives,
        missed=missed,
        fp_by_type=dict(Counter(why for _, why in false_positives)),
        nondefects_ignored=dict(ignored),
    )
