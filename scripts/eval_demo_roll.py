"""Score a trained model (ONNX) on the demo sample roll (data/sample_roll, rendered from held-out AITEX fabric
02) the way the live app runs it: frames through the Runner, then evaluated against the roll's answer key.

    backend/.venv/bin/python scripts/eval_demo_roll.py data/model/threadeye_s.onnx [--quiet]

Prints every reported defect / non-defect, the truth, and the evaluation (found, false alarms, nuisances).
Run from the repository root; the model's model_info.json (classes, thresholds) must sit next to the .onnx.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from threadeye.core.evaluation import Prediction, evaluate  # noqa: E402
from threadeye.core.providers import ProviderContext  # noqa: E402
from threadeye.core.runner import RollSpec, Runner  # noqa: E402
from threadeye.core.scoring.profile import simulator_parity_profile  # noqa: E402
from threadeye.datasets.answer_key import load_answer_key  # noqa: E402
from threadeye.providers.local_model import LocalModelDetector  # noqa: E402
from threadeye.services.benchmark import truth_from_key  # noqa: E402
from threadeye.sources.simulated_roll import VideoFileSource  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", type=Path)
    ap.add_argument("--roll", type=Path, default=ROOT / "data/sample_roll")
    ap.add_argument("--infer-scale", type=float, default=1.0, help="enlarge frames before tiling (tiny defects)")
    ap.add_argument("--quiet", action="store_true", help="only the evaluation line")
    args = ap.parse_args()

    key = load_answer_key(args.roll, require_media=True)
    source = VideoFileSource(args.roll)
    meta = source.parsed.meta
    det = LocalModelDetector({"model_path": str(args.model), "infer_scale": args.infer_scale}, ProviderContext())
    runner = Runner(source, det, simulator_parity_profile(),
                    RollSpec(width_in=meta.fabric_width_in, declared_length_yd=meta.roll_length_yd),
                    inspection_id="demo-eval")
    t = time.time()
    runner.run_to_end()
    truths, nuisances = truth_from_key(key, meta.px_per_cm)
    preds = []
    lines = []
    for tr in runner.deduper.tracks:
        v = runner.defect_view(tr)
        preds.append(Prediction(pred_id=tr.defect_no, cls=v["current_cls"], box=tr.box, is_defect=v["kind"] == "defect",
                                nondefect_category=v["nondefect_category"]))
        lines.append(f"  {tr.defect_no} {v['current_cls']:14s} {v['kind']:9s} {v['nondefect_category'] or '':12s} "
                     f"yd {v['center_yd']:.2f} across {v['across_start_cm']:.0f}-{v['across_end_cm']:.0f} cm")
    ev = evaluate(preds, truths, nuisances, fabric_width_cm=meta.fabric_width_cm,
                  selvage_band_cm=meta.selvage_band_px / meta.px_per_cm)
    if not args.quiet:
        print(f"{len(runner.track)} frames in {time.time() - t:.0f} s; reported:")
        print("\n".join(lines))
        print("truth:")
        for d in truths:
            print(f"  {d.defect_id} {d.cls:14s} yd {d.box.center_yd:.2f} "
                  f"across {d.box.across_start_cm:.0f}-{d.box.across_end_cm:.0f} cm")
        print("nuisances in the roll:", [n.type for n in nuisances])
    print(ev)


if __name__ == "__main__":
    main()
