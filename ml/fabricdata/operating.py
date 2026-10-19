"""Operating point and plain-language test numbers for the trained detector.

COCO AP averages over every score threshold; an inspector sees one. Here:

1. ``choose_thresholds`` picks, per class, the score threshold with the best F1 on **val**.
2. ``report`` applies those thresholds to **test** and counts what an inspector would see: how many real
   defects are found (with the right class, and by any defect class), how many boxes are false alarms, and
   how often a non-defect (sticker, hand, ...) is called a defect; per class and per source.

Matching: a detection hits a ground-truth box of the same class when IoU >= ``IOU`` or its centre lies inside
the box (long thin yarn faults give low IoU even when found). Each truth box is matched once, best score
first; further boxes on an already found truth are duplicates (the app merges them) and are not counted.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

IOU = 0.3
GRID = [round(0.05 * i, 2) for i in range(1, 20)]
DEFAULT_THRESHOLD = 0.3

Box = tuple[float, float, float, float]


@dataclass(frozen=True)
class Det:
    image: str
    cls: str
    score: float
    box: Box


@dataclass(frozen=True)
class Truth:
    image: str
    cls: str
    box: Box


def iou(a: Box, b: Box) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def hits(d: Box, t: Box) -> bool:
    cx, cy = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
    return iou(d, t) >= IOU or (t[0] <= cx <= t[2] and t[1] <= cy <= t[3])


def _by_image(items: Iterable[Det | Truth]) -> dict[str, list]:
    out: dict[str, list] = defaultdict(list)
    for x in items:
        out[x.image].append(x)
    return out


def match(dets: Sequence[Det], truths: Sequence[Truth], same_class: Callable[[str, str], bool]) -> tuple[set, set, set]:
    """(found truth ids, true-positive det ids, duplicate det ids); ids are positions in the inputs."""
    t_img = _by_image(truths)
    t_index = {id(t): i for i, t in enumerate(truths)}
    found: set[int] = set()
    tp: set[int] = set()
    dup: set[int] = set()
    for k in sorted(range(len(dets)), key=lambda i: -dets[i].score):
        d = dets[k]
        cands = [t for t in t_img.get(d.image, []) if same_class(d.cls, t.cls) and hits(d.box, t.box)]
        free = [t for t in cands if t_index[id(t)] not in found]
        if free:
            best = max(free, key=lambda t: iou(d.box, t.box))
            found.add(t_index[id(best)])
            tp.add(k)
        elif cands:
            dup.add(k)
    return found, tp, dup


def choose_thresholds(dets: Sequence[Det], truths: Sequence[Truth], classes: Sequence[str]) -> dict[str, float]:
    out = {}
    for c in classes:
        tc = [t for t in truths if t.cls == c]
        if not tc:
            out[c] = DEFAULT_THRESHOLD
            continue
        dc_all = [d for d in dets if d.cls == c]
        best = (-1.0, DEFAULT_THRESHOLD)
        for thr in GRID:
            dc = [d for d in dc_all if d.score >= thr]
            found, tp, dup = match(dc, tc, lambda a, b: a == b)
            fp = len(dc) - len(tp) - len(dup)
            p = len(tp) / max(len(tp) + fp, 1)
            r = len(found) / len(tc)
            f1 = 2 * p * r / (p + r) if p + r else 0.0
            if f1 > best[0]:
                best = (f1, thr)
        out[c] = best[1]
    return out


def report(dets: Sequence[Det], truths: Sequence[Truth], thresholds: Mapping[str, float], defect_classes: set[str],
           source_of: Callable[[str], str], images: Iterable[str]) -> dict:
    """Test numbers at the chosen thresholds, overall, per class and per source."""
    kept = [d for d in dets if d.score >= thresholds.get(d.cls, DEFAULT_THRESHOLD)]
    all_images = set(images)
    is_def = lambda c: c in defect_classes  # noqa: E731
    d_def = [d for d in kept if is_def(d.cls)]
    t_def = [t for t in truths if is_def(t.cls)]
    t_non = [t for t in truths if not is_def(t.cls)]

    found_cls, tp_cls, dup_cls = match(d_def, t_def, lambda a, b: a == b)
    found_any, tp_any, dup_any = match(d_def, t_def, lambda a, b: True)
    false_alarm = [k for k in range(len(d_def)) if k not in tp_any and k not in dup_any]
    # A non-defect called a defect: a defect-class box on a sticker / thread / wrinkle / hand.
    nd_found, _, _ = match(d_def, t_non, lambda a, b: True)

    def rate(n: int, total: int) -> float | None:
        return round(n / total, 4) if total else None

    per_class = {}
    for c in sorted({t.cls for t in truths} | {d.cls for d in kept}):
        tc = [i for i, t in enumerate(t_def) if t.cls == c] if is_def(c) else []
        dc = [k for k, d in enumerate(d_def) if d.cls == c]
        per_class[c] = {
            "threshold": thresholds.get(c, DEFAULT_THRESHOLD),
            "truth": len(tc) if is_def(c) else sum(t.cls == c for t in truths),
            "recall": rate(sum(i in found_cls for i in tc), len(tc)) if is_def(c) else None,
            "precision": rate(sum(k in tp_cls for k in dc), sum(k not in dup_cls for k in dc)) if is_def(c) else None,
        }
        if not is_def(c):  # a non-defect class: how often the model names it correctly
            dn = [d for d in kept if d.cls == c]
            tn = [t for t in truths if t.cls == c]
            f, tp, dup = match(dn, tn, lambda a, b: a == b)
            per_class[c].update(recall=rate(len(f), len(tn)), precision=rate(len(tp), len(dn) - len(dup)))

    per_source: dict[str, dict] = {}
    src_imgs: dict[str, set[str]] = defaultdict(set)
    for im in all_images:
        src_imgs[source_of(im)].add(im)
    for s, ims in sorted(src_imgs.items()):
        ti = [i for i, t in enumerate(t_def) if t.image in ims]
        fa = [k for k in false_alarm if d_def[k].image in ims]
        per_source[s] = {
            "tiles": len(ims),
            "defects": len(ti),
            "found_any_class": rate(sum(i in found_any for i in ti), len(ti)),
            "found_right_class": rate(sum(i in found_cls for i in ti), len(ti)),
            "false_alarms_per_100_tiles": round(100 * len(fa) / len(ims), 2),
        }
    return {
        "matching": f"same class and IoU >= {IOU} or detection centre inside the truth box",
        "tiles": len(all_images),
        "defects": len(t_def),
        "found_any_class": rate(len(found_any), len(t_def)),
        "found_right_class": rate(len(found_cls), len(t_def)),
        "defect_boxes": len(d_def),
        "precision": rate(len(tp_any), len(tp_any) + len(false_alarm)),
        "false_alarms": len(false_alarm),
        "false_alarms_per_100_tiles": round(100 * len(false_alarm) / max(len(all_images), 1), 2),
        "nondefects": len(t_non),
        "nondefects_called_defect": rate(len(nd_found), len(t_non)),
        "per_class": per_class,
        "per_source": per_source,
    }
