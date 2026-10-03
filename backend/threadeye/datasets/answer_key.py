"""RESTRICTED: access to a simulated roll's answer key (ground truth + non-defect distractions).

Only ``threadeye.providers.simulated`` and the verification/benchmark services may import this
module (import-linter contract in pyproject.toml). The detection pipeline, API, DB layer and reports
must never depend on ground truth, so a real detector can replace the simulator without changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from threadeye.datasets.contracts import (
    GroundTruthRow,
    NuisanceRow,
    ValidationReport,
    validate_dataset,
)


@dataclass(frozen=True)
class AnswerKey:
    dataset_dir: str
    defects: tuple[GroundTruthRow, ...]
    nuisances: tuple[NuisanceRow, ...]
    is_simulated: bool = True


class InvalidDataset(ValueError):
    def __init__(self, report: ValidationReport) -> None:
        super().__init__("; ".join(str(e) for e in report.errors[:5]))
        self.report = report


def load_answer_key(directory: str | Path, *, require_media: bool = True) -> AnswerKey:
    report, parsed = validate_dataset(directory, require_media=require_media)
    if parsed is None:
        raise InvalidDataset(report)
    return AnswerKey(
        dataset_dir=str(Path(directory)),
        defects=tuple(parsed.ground_truth),
        nuisances=tuple(parsed.nuisance),
    )
