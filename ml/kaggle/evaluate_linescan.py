"""Production-pipeline video evaluation with a supplied real detector (GPU or CPU)."""

from __future__ import annotations

from collections import Counter

from threadeye.core.evaluation import Prediction, evaluate
from threadeye.core.providers import ProviderContext
from threadeye.core.runner import RollSpec, Runner
from threadeye.core.scoring.profile import simulator_parity_profile
from threadeye.datasets.answer_key import load_answer_key
from threadeye.providers.local_model import LocalModelDetector
from threadeye.services.benchmark import truth_from_key
from threadeye.sources.simulated_roll import VideoFileSource


class TorchDetector(LocalModelDetector):
    def __init__(self, config, model):
        super().__init__(config, ProviderContext())
        self.model = model

    def prepare(self, source):
        self._any_size = self.whole_strip

    def run(self, batch):
        import torch

        with torch.no_grad():
            return (
                self.model(torch.from_numpy(batch).cuda().half()).float().cpu().numpy()
            )


def video_metrics(detector, directory):
    source = VideoFileSource(directory)
    meta = source.parsed.meta
    key = load_answer_key(directory, require_media=True)
    truths, nuisances = truth_from_key(key, meta.px_per_cm)
    runner = Runner(
        source,
        detector,
        simulator_parity_profile(),
        RollSpec(meta.fabric_width_in, meta.roll_length_yd),
        inspection_id="offline-round3-validation",
    )
    try:
        runner.run_to_end()
    finally:
        source.close()
    predictions = []
    for t in runner.deduper.tracks:
        view = runner.defect_view(t)
        predictions.append(
            Prediction(
                t.defect_no,
                view["current_cls"],
                t.box,
                view["kind"] == "defect",
                view["nondefect_category"],
            )
        )
    result = evaluate(
        predictions,
        truths,
        nuisances,
        fabric_width_cm=meta.fabric_width_cm,
        selvage_band_cm=meta.selvage_band_px / meta.px_per_cm,
    )
    pm = {p.pred_id: p for p in predictions}
    tm = {t.defect_id: t for t in truths}
    matches = [
        {
            "prediction": pid,
            "truth": tid,
            "predicted_class": pm[pid].cls,
            "truth_class": tm[tid].cls,
            "right_class": pm[pid].cls == tm[tid].cls,
            "iou": iou,
        }
        for pid, tid, iou in result.matches
    ]
    broken = sum(t.cls == "broken_yarn" for t in truths)
    right = sum(m["truth_class"] == "broken_yarn" and m["right_class"] for m in matches)
    return {
        "dataset": directory.name,
        "tp": result.tp,
        "fp": result.fp,
        "fn": result.fn,
        "broken_truth": broken,
        "broken_right": right,
        "precision": result.precision,
        "recall": result.recall,
        "matches": matches,
        "missed": result.missed,
        "false_alert_types": result.fp_by_type,
        "class_confusion": dict(
            Counter(f"{m['truth_class']}->{m['predicted_class']}" for m in matches)
        ),
    }


def aggregate(rows):
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    n = sum(r["broken_truth"] for r in rows)
    return {
        "precision": tp / (tp + fp) if tp + fp else 1,
        "recall": tp / (tp + fn) if tp + fn else 1,
        "broken_right_recall": sum(r["broken_right"] for r in rows) / n if n else 0,
        "false_alarms": fp,
        "broken_truth": n,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }
