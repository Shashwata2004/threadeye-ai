#!/usr/bin/env python3
"""
Compare ThreadEye detections against the simulator's ground truth.

Two prediction formats are accepted (CSV with a header row):

  Roll level (already de-duplicated by your app):
      center_yd, [across_cm], [class], [confidence], [length_in]

  Frame level (raw detections per sampled frame, pixel coords in the camera view without the info bar):
      frame, x0, y0, x1, y1, [class], [confidence]
      These are converted to roll positions with frames.csv (fabric position and sideways offset of
      every frame) and the same defect seen in several frames is merged into one before matching.

  With roll_meta.json, false positives are also explained when they land on something that is not a
  defect but exists on real rolls: loose threads, wrinkles, inspector stickers, the selvage edge.

Usage:
  python evaluate.py --gt sim_out/ground_truth.csv --pred my_preds.csv --meta sim_out/roll_meta.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

CM_PER_YARD = 91.44
CM_PER_INCH = 2.54


def four_point(length_in: float, is_hole: bool) -> int:
    if is_hole:
        return 2 if length_in <= 1.0 else 4
    if length_in <= 3:
        return 1
    if length_in <= 6:
        return 2
    if length_in <= 9:
        return 3
    return 4


def roll_score(items: list[dict], roll_yd: float, width_in: float) -> tuple[int, float]:
    per_yard: dict[int, int] = defaultdict(int)
    for d in items:
        if d.get("points") is not None:
            per_yard[int(d["center_yd"])] += d["points"]
    total = sum(min(4, v) for v in per_yard.values())
    return total, total * 3600 / (roll_yd * width_in)


def iou(a: dict, b: dict) -> float:
    ix = max(0.0, min(a["x1"], b["x1"]) - max(a["x0"], b["x0"]))
    iy = max(0.0, min(a["ry1"], b["ry1"]) - max(a["ry0"], b["ry0"]))
    inter = ix * iy
    area = lambda d: max(1e-6, (d["x1"] - d["x0"]) * (d["ry1"] - d["ry0"]))
    return inter / (area(a) + area(b) - inter)


def frame_positions(meta: dict, meta_path: Path):
    """Per-frame roll position and fabric sideways offset, from frames.csv (falls back to constant speed)."""
    fcsv = meta_path.parent / meta.get("frames_csv", "frames.csv")
    if fcsv.exists():
        tops, x0s = {}, {}
        for r in csv.DictReader(open(fcsv)):
            tops[int(r["frame"])] = int(r["roll_y_top_px"])
            x0s[int(r["frame"])] = int(r.get("fabric_x0_px") or 0)
        return (lambda f: tops[f]), (lambda f: x0s[f])
    ppf = meta.get("px_per_frame") or meta["px_per_frame_at_full_speed"]
    return (lambda f: round(f * ppf)), (lambda f: 0)


def load_frame_level(rows: list[dict], meta: dict, meta_path: Path, merge_cm: float) -> list[dict]:
    """Convert per-frame boxes (pixel coords in the camera view) to roll coordinates and merge repeated
    sightings of the same defect. Two boxes are the same defect if they overlap well (IoU > 0.3) or
    their centres are within merge_cm."""
    ppc = meta["px_per_cm"]
    top_of, x0_of = frame_positions(meta, meta_path)
    dets = []
    for r in rows:
        f = int(float(r["frame"]))
        top, off = top_of(f), x0_of(f)
        x0, y0, x1, y1 = (float(r[k]) for k in ("x0", "y0", "x1", "y1"))
        dets.append({
            "ry0": top + y0, "ry1": top + y1, "x0": x0 - off, "x1": x1 - off,
            "class": (r.get("class") or "").strip(),
            "confidence": float(r["confidence"]) if r.get("confidence") else None,
        })
    dets.sort(key=lambda d: (d["ry0"] + d["ry1"]) / 2)
    clusters: list[dict] = []
    merge_px = merge_cm * ppc
    for d in dets:
        cy, cx = (d["ry0"] + d["ry1"]) / 2, (d["x0"] + d["x1"]) / 2
        best = None
        for c in reversed(clusters):
            ccy, ccx = (c["ry0"] + c["ry1"]) / 2, (c["x0"] + c["x1"]) / 2
            if cy - ccy > max(merge_px, c["ry1"] - c["ry0"]) * 2:
                break
            if iou(d, c) > 0.3 or (abs(cy - ccy) <= merge_px and abs(cx - ccx) <= merge_px):
                best = c
                break
        if best is None:
            clusters.append({**d, "classes": [d["class"]], "hits": 1})
            continue
        n = best["hits"]
        for k in ("ry0", "ry1", "x0", "x1"):
            best[k] = (best[k] * n + d[k]) / (n + 1)
        best["classes"].append(d["class"])
        if d["confidence"] is not None:
            best["confidence"] = max(best["confidence"] or 0.0, d["confidence"])
        best["hits"] = n + 1
    out = []
    for c in clusters:
        cls = Counter(x for x in c["classes"] if x).most_common(1)
        w_cm, h_cm = (c["x1"] - c["x0"]) / ppc, (c["ry1"] - c["ry0"]) / ppc
        out.append({
            "center_yd": (c["ry0"] + c["ry1"]) / 2 / ppc / CM_PER_YARD,
            "across_cm": (c["x0"] + c["x1"]) / 2 / ppc,
            "class": cls[0][0] if cls else "",
            "confidence": c["confidence"],
            "length_in": max(w_cm, h_cm) / CM_PER_INCH,
            "frames_merged": c["hits"],
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Score detections against simulator ground truth.")
    ap.add_argument("--gt", required=True)
    ap.add_argument("--pred", required=True)
    ap.add_argument("--meta", help="roll_meta.json (required for frame-level predictions and roll score)")
    ap.add_argument("--tol-yd", type=float, default=0.15, help="max distance along the roll for a match (yards)")
    ap.add_argument("--tol-cm", type=float, default=15.0, help="max distance across the width for a match (cm)")
    ap.add_argument("--merge-cm", type=float, default=3.0,
                    help="frame-level only: sightings closer than this are treated as the same defect")
    ap.add_argument("--class-aware", action="store_true", help="a match also needs the same class name")
    ap.add_argument("--min-length-in", type=float, default=0.0,
                    help="ignore ground-truth defects smaller than this (too small to see at this resolution)")
    ap.add_argument("--out", default="eval_matches.csv")
    args = ap.parse_args()

    gt = []
    for r in csv.DictReader(open(args.gt)):
        if float(r["length_in"]) < args.min_length_in:
            continue
        gt.append({"id": int(r["defect_id"]), "class": r["class"], "center_yd": float(r["center_yd"]),
                   "across_cm": float(r["across_cm"]), "length_in": float(r["length_in"]),
                   "points": int(r["points"])})
    rows = list(csv.DictReader(open(args.pred)))
    meta = json.load(open(args.meta)) if args.meta else None
    if rows and "frame" in rows[0]:
        if not meta:
            raise SystemExit("Frame-level predictions need --meta roll_meta.json")
        preds = load_frame_level(rows, meta, Path(args.meta), args.merge_cm)
    else:
        preds = [{
            "center_yd": float(r["center_yd"]),
            "across_cm": float(r["across_cm"]) if r.get("across_cm") else None,
            "class": (r.get("class") or "").strip(),
            "confidence": float(r["confidence"]) if r.get("confidence") else None,
            "length_in": float(r["length_in"]) if r.get("length_in") else None,
        } for r in rows]

    pairs = []
    for gi, g in enumerate(gt):
        for pi, p in enumerate(preds):
            dy = abs(g["center_yd"] - p["center_yd"])
            if dy > args.tol_yd:
                continue
            dx = abs(g["across_cm"] - p["across_cm"]) if p["across_cm"] is not None else 0.0
            if dx > args.tol_cm:
                continue
            if args.class_aware and p["class"] and p["class"].lower() != g["class"].lower():
                continue
            pairs.append((dy / args.tol_yd + dx / args.tol_cm, gi, pi))
    pairs.sort()
    g_used, p_used, matches = {}, {}, []
    for _, gi, pi in pairs:
        if gi in g_used or pi in p_used:
            continue
        g_used[gi], p_used[pi] = pi, gi
        matches.append((gi, pi))

    tp = len(matches)
    fp = len(preds) - tp
    fn = len(gt) - tp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    print(f"Ground truth defects : {len(gt)}" + (f" (ignoring < {args.min_length_in} in)" if args.min_length_in else ""))
    print(f"Predicted defects    : {len(preds)}")
    print(f"True positives       : {tp}")
    print(f"False positives      : {fp}")
    print(f"Missed (false neg.)  : {fn}")
    print(f"Precision            : {precision:.3f}")
    print(f"Recall               : {recall:.3f}")
    print(f"F1                   : {f1:.3f}")

    by_class = defaultdict(lambda: [0, 0])
    for gi, g in enumerate(gt):
        by_class[g["class"]][1] += 1
        if gi in g_used:
            by_class[g["class"]][0] += 1
    print("\nRecall by class:")
    for cls, (hit, total) in sorted(by_class.items()):
        print(f"  {cls:<16} {hit}/{total}  ({hit / total:.0%})")

    if matches and any(preds[pi]["class"] for _, pi in matches):
        correct = sum(1 for gi, pi in matches if preds[pi]["class"].lower() == gt[gi]["class"].lower())
        print(f"\nClass accuracy on matched defects: {correct}/{tp} ({correct / tp:.0%})")

    if meta:
        holes = meta.get("hole_classes")
        hole_set = {h.lower() for h in holes} if isinstance(holes, list) else None

        def is_hole(c: str) -> bool:
            return c.lower() in hole_set if hole_set else "hole" in c.lower()

        for p in preds:
            p["points"] = four_point(p["length_in"], is_hole(p["class"])) if p.get("length_in") is not None else None
        if all(p["points"] is not None for p in preds):
            roll_yd, width_in = meta["roll_length_yd"], meta["fabric_width_in"]
            thr = meta["expected_score"]["threshold"]
            gt_total, gt_per100 = roll_score(gt, roll_yd, width_in)
            pr_total, pr_per100 = roll_score(preds, roll_yd, width_in)
            print("\n4-point roll score:")
            print(f"  ground truth : {gt_total} pts, {gt_per100:.1f} /100 sq yd -> {'PASS' if gt_per100 <= thr else 'FAIL'}")
            print(f"  predicted    : {pr_total} pts, {pr_per100:.1f} /100 sq yd -> {'PASS' if pr_per100 <= thr else 'FAIL'}")

    fp_reason = {}
    if meta:
        ncsv = Path(args.meta).parent / meta.get("nuisance_csv", "nuisance.csv")
        nuis = list(csv.DictReader(open(ncsv))) if ncsv.exists() else []
        width_cm = meta.get("fabric_width_cm", 0)
        edge_cm = max(1.5, meta.get("selvage_band_px", 0) / meta["px_per_cm"] + 0.5)
        for pi, p in enumerate(preds):
            if pi in p_used:
                continue
            reason = "unexplained"
            best = None
            for n in nuis:
                dy = abs(float(n["center_yd"]) - p["center_yd"]) * CM_PER_YARD
                reach = max(args.tol_cm, float(n["extent_cm"]))
                dx = abs(float(n["across_cm"]) - p["across_cm"]) if p["across_cm"] is not None else 0.0
                if dy <= reach and dx <= reach and (best is None or dy + dx < best[0]):
                    best = (dy + dx, n["type"])
            if best:
                reason = best[1]
            elif p["across_cm"] is not None and width_cm and (p["across_cm"] < edge_cm or p["across_cm"] > width_cm - edge_cm):
                reason = "selvage_edge"
            fp_reason[pi] = reason
        if fp_reason:
            print("\nFalse positives explained (what the AI mistook for a defect):")
            for reason, count in Counter(fp_reason.values()).most_common():
                print(f"  {reason:<16} {count}")

    with open(args.out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["status", "gt_id", "gt_class", "gt_center_yd", "pred_class", "pred_center_yd", "pred_confidence",
                    "fp_likely_cause"])
        for gi, g in enumerate(gt):
            if gi in g_used:
                p = preds[g_used[gi]]
                w.writerow(["TP", g["id"], g["class"], g["center_yd"], p["class"], round(p["center_yd"], 3),
                            p["confidence"], ""])
            else:
                w.writerow(["FN", g["id"], g["class"], g["center_yd"], "", "", "", ""])
        for pi, p in enumerate(preds):
            if pi not in p_used:
                w.writerow(["FP", "", "", "", p["class"], round(p["center_yd"], 3), p["confidence"],
                            fp_reason.get(pi, "")])
    print(f"\nDetails written to {args.out}")


if __name__ == "__main__":
    main()
