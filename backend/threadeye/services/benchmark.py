"""Run a whole simulated roll headless and measure it against its answer key.

Used by the CLI (``threadeye run-sample``), the integration tests, and later the daily verification run
and the benchmark page. This service may read the answer key (import-linter allows it): it feeds the
simulated detector and scores the result. The pipeline itself never sees ground truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from threadeye.core.evaluation import EvalResult, Prediction, TruthDefect, TruthNuisance, evaluate
from threadeye.core.geometry import YARD_CM, RollBox
from threadeye.core.providers import ProviderContext
from threadeye.core.runner import RollSpec, Runner, RunnerEvent
from threadeye.core.scoring.four_point import RollGeometry, ScorableDefect, ScoreResult, score_roll
from threadeye.core.scoring.profile import RuleProfile, simulator_parity_profile
from threadeye.core.taxonomy import load_default_taxonomy
from threadeye.datasets.answer_key import AnswerKey, load_answer_key
from threadeye.providers.registry import create_provider
from threadeye.providers.simulated import PRESETS, SimulatedDetector
from threadeye.sources.simulated_roll import TrackFrameSource, VideoFileSource


@dataclass
class RollRun:
    dataset: str
    provider_label: str
    preset: Mapping[str, Any]
    profile_name: str
    frames: int
    frames_sampled: int
    coverage_pct: float
    runner: Runner
    events: list[RunnerEvent]
    score: ScoreResult
    expected: dict[str, Any]
    truth_score: ScoreResult
    evaluation: EvalResult
    defects: list[dict[str, Any]] = field(default_factory=list)

    @property
    def matches_expected(self) -> bool:
        e = self.expected
        return bool(
            self.score.total_points == e["total_points"]
            and round(self.score.per_100, 2) == round(e["points_per_100_sq_yd"], 2)
            and self.score.verdict == e["verdict"]
        )


def truth_from_key(key: AnswerKey, px_per_cm: float) -> tuple[list[TruthDefect], list[TruthNuisance]]:
    taxonomy = load_default_taxonomy()
    defects = [
        TruthDefect(
            defect_id=d.defect_id,
            cls=taxonomy.resolve(d.cls),
            box=RollBox(d.y0_px / px_per_cm, d.y1_px / px_per_cm, d.x0_px / px_per_cm, d.x1_px / px_per_cm),
            points=d.points,
        )
        for d in key.defects
    ]
    nuisances = []
    for n in key.nuisances:
        half = n.extent_cm / 2
        c = n.center_yd * YARD_CM
        nuisances.append(TruthNuisance(n.type, RollBox(c - half, c + half, n.across_cm - half, n.across_cm + half)))
    return defects, nuisances


def score_answer_key(key: AnswerKey, px_per_cm: float, geometry: RollGeometry, profile: RuleProfile) -> ScoreResult:
    """Score the answer key itself (what a perfect detector + inspector would get)."""
    taxonomy = load_default_taxonomy()
    truths, _ = truth_from_key(key, px_per_cm)
    items = [
        ScorableDefect(
            defect_id=t.defect_id,
            cls=t.cls,
            is_hole=bool(taxonomy.classes.get(t.cls) and taxonomy.classes[t.cls].is_hole),
            length_in=t.box.length_in,
            start_yd=t.box.start_yd,
            end_yd=t.box.end_yd,
            center_yd=t.box.center_yd,
            across_start_cm=t.box.across_start_cm,
            across_end_cm=t.box.across_end_cm,
        )
        for t in truths
    ]
    return score_roll(items, geometry, profile)


def run_roll(
    directory: str | Path,
    *,
    preset: str | Mapping[str, Any] = "perfect",
    profile: RuleProfile | None = None,
    use_video: bool = False,
    confirm_all: bool = True,
    provider_id: str = "simulated",
    provider_config: Mapping[str, Any] | None = None,
) -> RollRun:
    directory = Path(directory)
    config = PRESETS[preset] if isinstance(preset, str) else preset
    profile = profile or simulator_parity_profile()
    key = load_answer_key(directory, require_media=use_video)
    source = VideoFileSource(directory) if use_video or provider_id != "simulated" else TrackFrameSource(directory)
    meta = source.parsed.meta
    provider = (
        SimulatedDetector(config, ProviderContext(seed=int(config.get("seed", 0)), answer_key=key))
        if provider_id == "simulated"
        else create_provider(provider_id, provider_config, ProviderContext(extras={"dataset_dir": str(directory)}))
    )
    runner = Runner(
        source,
        provider,
        profile,
        RollSpec(width_in=meta.fabric_width_in, declared_length_yd=meta.roll_length_yd),
        inspection_id=f"headless:{directory.name}",
    )
    events = runner.run_to_end()
    if confirm_all:
        runner.confirm_all()
    score = runner.score(final=confirm_all)
    assert score is not None

    truths, nuisances = truth_from_key(key, meta.px_per_cm)
    preds = []
    for t in runner.deduper.tracks:
        view = runner.defect_view(t)
        preds.append(
            Prediction(
                pred_id=t.defect_no,
                cls=view["current_cls"],
                box=t.box,
                is_defect=view["kind"] == "defect",
                nondefect_category=view["nondefect_category"],
            )
        )
    geometry = RollGeometry(meta.roll_length_yd, meta.fabric_width_in, meta.fabric_width_cm)
    band_cm = meta.selvage_band_px / meta.px_per_cm
    evaluation = evaluate(preds, truths, nuisances, fabric_width_cm=meta.fabric_width_cm, selvage_band_cm=band_cm)
    return RollRun(
        dataset=directory.name,
        provider_label=provider.info.label,
        preset=config,
        profile_name=profile.name,
        frames=len(runner.track),
        frames_sampled=len(runner.plan.samples),
        coverage_pct=round(runner.coverage() * 100, 1),
        runner=runner,
        events=events,
        score=score,
        expected=meta.expected_score.model_dump(),
        truth_score=score_answer_key(key, meta.px_per_cm, geometry, profile),
        evaluation=evaluation,
        defects=[runner.defect_view(t, score.defects[t.defect_no].points) for t in runner.deduper.tracks],
    )
