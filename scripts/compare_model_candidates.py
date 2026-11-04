"""Conservative, predeclared candidate checks; never activates or publishes a model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def compare(baseline: dict, candidate: dict, base_tiles: dict, candidate_tiles: dict) -> dict:
    reasons = []
    old = {r["dataset"]: r for r in baseline["rolls"]}
    new = {r["dataset"]: r for r in candidate["rolls"]}
    if old.keys() != new.keys():
        raise ValueError("candidate and baseline roll suites differ")
    rows = []
    for name, before in old.items():
        after = new[name]
        for key, value in before["sha256"].items():
            if not key.endswith(".onnx") and key != "model_info.json" and after["sha256"].get(key) != value:
                raise ValueError(f"{name}: input changed: {key}")
        if before.get("inference_threads") != after.get("inference_threads"):
            raise ValueError("inference configurations differ")
        a, b = before["evaluation"], after["evaluation"]
        rows.append({"dataset": name, "before": {k: a[k] for k in ("tp", "fp", "fn", "recall", "precision")},
                     "after": {k: b[k] for k in ("tp", "fp", "fn", "recall", "precision")}})
    if sum(r["after"]["fn"] for r in rows) >= sum(r["before"]["fn"] for r in rows):
        reasons.append("roll-suite misses did not decrease")
    if sum(r["after"]["fp"] for r in rows) > sum(r["before"]["fp"] for r in rows):
        reasons.append("roll-suite false alarms increased")
    for name in old:
        if new[name]["evaluation"]["tp"] < old[name]["evaluation"]["tp"]:
            reasons.append(f"{name}: fewer true defects found")
    decisions_before = [r["decision_replay"] for r in old.values() if "decision_replay" in r]
    decisions_after = [new[name]["decision_replay"] for name in old if "decision_replay" in old[name]]
    if sum(not d["verdict_agrees"] for d in decisions_after) > sum(not d["verdict_agrees"] for d in decisions_before):
        reasons.append("more model-only roll verdicts disagree with the answer-key oracle")
    if sum(abs(d["model_per_100"] - d["oracle_per_100"]) for d in decisions_after) > sum(abs(d["model_per_100"] - d["oracle_per_100"]) for d in decisions_before) + 0.01:
        reasons.append("roll score error increased")
    for field in ("tiles", "defects"):
        if base_tiles[field] != candidate_tiles[field]:
            raise ValueError(f"overall test population changed: {field}")
    for field in ("found_any_class", "found_right_class"):
        if candidate_tiles[field] < base_tiles[field]:
            reasons.append(f"overall {field} decreased")
    if candidate_tiles["precision"] < base_tiles["precision"] - 0.02:
        reasons.append("overall precision decreased by more than 2 percentage points")
    if candidate_tiles["false_alarms_per_100_tiles"] > base_tiles["false_alarms_per_100_tiles"] + 1:
        reasons.append("overall false alarms increased by more than 1 per 100 tiles")
    if candidate_tiles["nondefects_called_defect"] > base_tiles["nondefects_called_defect"]:
        reasons.append("more nuisance objects called fabric defects")
    for cls in ("broken_yarn", "crease_mark"):
        if candidate_tiles["per_class"][cls]["recall"] < base_tiles["per_class"][cls]["recall"]:
            reasons.append(f"{cls}: overall recall decreased")
    return {"qualified_for_review": not reasons, "reasons": reasons, "rolls": rows,
            "baseline_model_sha256": baseline["model_sha256"], "candidate_model_sha256": candidate["model_sha256"],
            "limitation": "Regression and held-out tile evidence, not a factory pilot. A candidate is staged; the running model is unchanged."}


def markdown(result: dict, baseline: dict, candidate: dict, base_tiles: dict, candidate_tiles: dict) -> str:
    old = {r["dataset"]: r for r in baseline["rolls"]}
    new = {r["dataset"]: r for r in candidate["rolls"]}
    lines = ["# পুরোনো ও নতুন মডেলের তুলনা", "",
             "একই চারটি সিমুলেটেড ভিডিওতে real model inference। এটি কারখানার মাপা ফল নয়।",
             "",
             "**ফল:** " + ("নতুন মডেল নির্ধারিত তুলনার শর্ত পূরণ করেছে।" if result["qualified_for_review"] else "নতুন মডেল সব তুলনার শর্ত পূরণ করেনি; বর্তমান মডেল প্রতিস্থাপন করা হয়নি।"),
             "", "| ভিডিও | মোট ত্রুটি | আগে ধরা | এখন ধরা | আগে মিস | এখন মিস | আগে ভুল সতর্কতা | এখন ভুল সতর্কতা |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in result["rolls"]:
        a, b = row["before"], row["after"]
        lines.append(f"| {row['dataset']} | {a['tp'] + a['fn']} | {a['tp']} | {b['tp']} | {a['fn']} | {b['fn']} | {a['fp']} | {b['fp']} |")
    lines += ["", "## আগের linescan_roll ভিডিও", ""]
    if "linescan_roll" in old:
        a, b = old["linescan_roll"]["evaluation"], new["linescan_roll"]["evaluation"]
        lines.append(f"আগে {a['tp']}/{a['tp'] + a['fn']}টি, এখন {b['tp']}/{b['tp'] + b['fn']}টি ত্রুটি ধরা পড়েছে। "
                     f"ভুল সতর্কতা {a['fp']} → {b['fp']}। শনাক্তের হার {a['recall']*100:.1f}% → {b['recall']*100:.1f}%।")
    lines += ["", "## আগের একই সামগ্রিক test dataset", "",
              "| মাপকাঠি | আগে | এখন |", "|---|---:|---:|"]
    for key, label in [("found_any_class", "আসল ত্রুটি শনাক্ত"), ("found_right_class", "সঠিক শ্রেণিসহ শনাক্ত"), ("precision", "সতর্কতার সঠিকতা")]:
        lines.append(f"| {label} | {base_tiles[key]*100:.2f}% | {candidate_tiles[key]*100:.2f}% |")
    lines.append(f"| প্রতি ১০০ ছবিতে ভুল সতর্কতা | {base_tiles['false_alarms_per_100_tiles']:.2f} | {candidate_tiles['false_alarms_per_100_tiles']:.2f} |")
    for cls, label in [("broken_yarn", "ছেঁড়া সুতা শনাক্ত"), ("crease_mark", "crease শনাক্ত")]:
        lines.append(f"| {label} | {base_tiles['per_class'][cls]['recall']*100:.2f}% | {candidate_tiles['per_class'][cls]['recall']*100:.2f}% |")
    if result["reasons"]:
        lines += ["", "## কোন শর্ত পূরণ হয়নি", "", *[f"- {reason}" for reason in result["reasons"]]]
    lines += ["", "কোনো test ছবি training-এ যোগ করা হয়নি। নতুন ভিডিওগুলো আগের held-out ছবির নতুন বিন্যাস; স্বাধীন নতুন physical-fabric test নয়।",
              "ত্রুটির শনাক্তকরণ বাড়লেও ভুল সতর্কতা, শ্রেণি, স্কোর বা PASS/FAIL খারাপ হয়েছে কি না আলাদা যাচাই করা হয়েছে।",
              "এই রিপোর্ট তৈরি করা মডেলকে স্বয়ংক্রিয়ভাবে অ্যাপে বসায় না।", "",
              f"পুরোনো model SHA256: `{result['baseline_model_sha256']}`",
              f"নতুন model SHA256: `{result['candidate_model_sha256']}`", ""]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-suite", type=Path, required=True)
    parser.add_argument("--candidate-suite", type=Path, required=True)
    parser.add_argument("--baseline-tiles", type=Path, required=True)
    parser.add_argument("--candidate-tiles", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    evidence = [json.loads(p.read_text()) for p in [args.baseline_suite, args.candidate_suite, args.baseline_tiles, args.candidate_tiles]]
    result = compare(*evidence)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(markdown(result, *evidence))
    print(json.dumps({"qualified_for_review": result["qualified_for_review"], "reasons": result["reasons"]}))


if __name__ == "__main__":
    main()
