"""Validators for the simulator's data contracts (brief §8, PLAN.md §2 "Simulator conventions").

A dataset directory (e.g. ``data/sample_roll/``) contains:
  roll_meta.json, frames.csv, ground_truth.csv, nuisance.csv, roll_video.mp4, roll_preview.png

``validate_dataset(path)`` parses everything, checks each row and the cross-file consistency, and
returns a report with errors (unusable) and warnings (usable, but worth a look). Ground-truth rows
are parsed here only to *validate the files*; runtime access to the answer key goes through
``threadeye.datasets.answer_key`` (restricted by import-linter).
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from threadeye.core.taxonomy import Taxonomy, load_default_taxonomy

YARD_CM = 91.44
INCH_CM = 2.54

FILES = {
    "meta": "roll_meta.json",
    "frames": "frames.csv",
    "ground_truth": "ground_truth.csv",
    "nuisance": "nuisance.csv",
    "video": "roll_video.mp4",
    "preview": "roll_preview.png",
}

FRAMES_COLUMNS = (
    "frame",
    "time_s",
    "roll_y_top_px",
    "top_yd",
    "bottom_yd",
    "speed_m_min",
    "state",
    "fabric_x0_px",
    "hand_visible",
)
GT_COLUMNS = (
    "defect_id",
    "class",
    "center_yd",
    "start_yd",
    "end_yd",
    "across_cm",
    "length_in",
    "points",
    "first_full_frame",
    "last_full_frame",
    "operator_stop_frame",
    "x0_px",
    "y0_px",
    "x1_px",
    "y1_px",
    "source",
)
NUISANCE_COLUMNS = ("type", "center_yd", "across_cm", "extent_cm", "appears_frame")


# --------------------------------------------------------------------------------------------- models
class _Row(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


def _to_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"1", "true", "yes", "y", "t"}:
        return True
    if s in {"0", "false", "no", "n", "f", ""}:
        return False
    raise ValueError(f"not a boolean: {v!r}")


def _blank_to_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str) and v.strip() in {"", "-1", "nan", "None", "none", "NaN"}:
        return None
    return v


class ViewRegion(_Row):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class ExpectedScore(_Row):
    total_points: int = Field(ge=0)
    points_per_100_sq_yd: float = Field(ge=0)
    threshold: float = Field(gt=0)
    verdict: Literal["PASS", "FAIL"]


class RollMeta(BaseModel):
    model_config = ConfigDict(extra="allow", frozen=True)

    px_per_cm: float = Field(gt=0)
    view_region: ViewRegion
    fabric_width_cm: float = Field(gt=0)
    fabric_width_in: float = Field(gt=0)
    roll_length_yd: float = Field(gt=0)
    fps: float = Field(gt=0)
    frames: int = Field(gt=0)
    expected_score: ExpectedScore
    selvage_band_px: float = Field(ge=0)
    mode: Literal["realistic", "clean"]


class FrameRow(_Row):
    frame: int = Field(ge=0)
    time_s: float = Field(ge=0)
    roll_y_top_px: float
    top_yd: float
    bottom_yd: float
    speed_m_min: float = Field(ge=0)
    state: Literal["running", "stopped"]
    fabric_x0_px: float
    hand_visible: bool

    @field_validator("hand_visible", mode="before")
    @classmethod
    def _parse_bool(cls, v: Any) -> bool:
        return _to_bool(v)

    @field_validator("state", mode="before")
    @classmethod
    def _lower_state(cls, v: Any) -> str:
        return str(v).strip().lower()


class GroundTruthRow(_Row):
    defect_id: str
    cls: str = Field(alias="class")
    center_yd: float
    start_yd: float
    end_yd: float
    across_cm: float
    length_in: float = Field(gt=0)
    points: int = Field(ge=1, le=4)
    first_full_frame: int | None = None
    last_full_frame: int | None = None
    operator_stop_frame: int | None = None
    x0_px: float
    y0_px: float
    x1_px: float
    y1_px: float
    source: str = ""

    @field_validator("first_full_frame", "last_full_frame", "operator_stop_frame", mode="before")
    @classmethod
    def _optional_frame(cls, v: Any) -> Any:
        return _blank_to_none(v)


class NuisanceRow(_Row):
    type: Literal["wrinkle", "loose_thread", "sticker"]
    center_yd: float
    across_cm: float
    extent_cm: float = Field(gt=0)
    appears_frame: int | None = Field(default=None, ge=0)
    """Empty in the simulator's CSV for things on the fabric from the start (wrinkles, threads);
    a frame number for stickers, which the inspector places during a stop."""

    @field_validator("type", mode="before")
    @classmethod
    def _lower_type(cls, v: Any) -> str:
        return str(v).strip().lower()

    @field_validator("appears_frame", mode="before")
    @classmethod
    def _optional_appears(cls, v: Any) -> Any:
        return _blank_to_none(v)


# --------------------------------------------------------------------------------------------- report
@dataclass(frozen=True)
class Issue:
    file: str
    message: str
    row: int | None = None

    def __str__(self) -> str:
        where = f"{self.file}:{self.row}" if self.row is not None else self.file
        return f"{where}: {self.message}"


@dataclass
class ValidationReport:
    path: str
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, file: str, msg: str, row: int | None = None) -> None:
        self.errors.append(Issue(file, msg, row))

    def warn(self, file: str, msg: str, row: int | None = None) -> None:
        self.warnings.append(Issue(file, msg, row))


@dataclass(frozen=True)
class ParsedDataset:
    meta: RollMeta
    frames: list[FrameRow]
    ground_truth: list[GroundTruthRow]
    nuisance: list[NuisanceRow]


# --------------------------------------------------------------------------------------------- parsing
def _read_csv[R: BaseModel](path: Path, columns: Iterable[str], model: type[R], report: ValidationReport) -> list[R]:
    rows: list[R] = []
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = [h.strip() for h in (reader.fieldnames or [])]
        missing = [c for c in columns if c not in header]
        if missing:
            report.error(path.name, f"missing columns: {', '.join(missing)}")
            return rows
        for i, raw in enumerate(reader, start=2):  # row 1 is the header
            clean = {k.strip(): (v.strip() if isinstance(v, str) else v) for k, v in raw.items() if k}
            try:
                rows.append(model.model_validate(clean))
            except ValidationError as exc:
                first = exc.errors()[0]
                loc = ".".join(str(p) for p in first["loc"])
                report.error(path.name, f"{loc}: {first['msg']}", row=i)
    return rows


def load_roll_meta(path: Path) -> RollMeta:
    return RollMeta.model_validate(json.loads(path.read_text(encoding="utf-8")))


def per_100(total_points: float, length_yd: float, width_in: float) -> float:
    return total_points * 3600.0 / (length_yd * width_in)


# --------------------------------------------------------------------------------------------- checks
def validate_dataset(
    directory: str | Path,
    *,
    require_media: bool = True,
    taxonomy: Taxonomy | None = None,
) -> tuple[ValidationReport, ParsedDataset | None]:
    """Validate a simulator dataset directory. ``require_media=False`` for CSV-only fixtures."""
    root = Path(directory)
    report = ValidationReport(path=str(root))
    tax = taxonomy or load_default_taxonomy()

    for key, name in FILES.items():
        p = root / name
        if not p.is_file() or p.stat().st_size == 0:
            if key in {"video", "preview"} and not require_media:
                report.warn(name, "missing (allowed for CSV-only fixtures)")
            elif key == "preview":
                report.warn(name, "missing (optional)")
            else:
                report.error(name, "missing or empty")
    if report.errors:
        return report, None

    try:
        meta = load_roll_meta(root / FILES["meta"])
    except (ValidationError, json.JSONDecodeError) as exc:
        report.error(FILES["meta"], f"invalid: {exc}".splitlines()[0])
        return report, None

    frames = _read_csv(root / FILES["frames"], FRAMES_COLUMNS, FrameRow, report)
    gt = _read_csv(root / FILES["ground_truth"], GT_COLUMNS, GroundTruthRow, report)
    nuis = _read_csv(root / FILES["nuisance"], NUISANCE_COLUMNS, NuisanceRow, report)
    if report.errors:
        return report, None

    _check_meta(meta, report)
    _check_frames(meta, frames, report)
    _check_ground_truth(meta, frames, gt, tax, report)
    _check_nuisance(meta, frames, nuis, report)

    report.summary = {
        "mode": meta.mode,
        "frames": len(frames),
        "fps": meta.fps,
        "duration_s": round(len(frames) / meta.fps, 2),
        "roll_length_yd": meta.roll_length_yd,
        "fabric_width_in": meta.fabric_width_in,
        "defects": len(gt),
        "defect_classes": sorted({d.cls for d in gt}),
        "nuisances": len(nuis),
        "stopped_frames": sum(1 for f in frames if f.state == "stopped"),
        "hand_frames": sum(1 for f in frames if f.hand_visible),
        "expected_score": meta.expected_score.model_dump(),
        "is_simulated": True,
    }
    parsed = ParsedDataset(meta=meta, frames=frames, ground_truth=gt, nuisance=nuis)
    return report, (parsed if report.ok else None)


def _close(a: float, b: float, tol: float) -> bool:
    return math.isclose(a, b, abs_tol=tol)


def _check_meta(meta: RollMeta, r: ValidationReport) -> None:
    f = FILES["meta"]
    if not _close(meta.fabric_width_in, meta.fabric_width_cm / INCH_CM, 0.05):
        r.error(f, f"fabric_width_in {meta.fabric_width_in} != fabric_width_cm/2.54")
    es = meta.expected_score
    expected = round(per_100(es.total_points, meta.roll_length_yd, meta.fabric_width_in), 2)
    if not _close(expected, es.points_per_100_sq_yd, 0.011):
        r.error(f, f"expected_score.points_per_100_sq_yd {es.points_per_100_sq_yd} != recomputed {expected}")
    verdict = "PASS" if round(es.points_per_100_sq_yd, 2) <= es.threshold else "FAIL"
    if verdict != es.verdict:
        r.error(f, f"expected_score.verdict {es.verdict} inconsistent with threshold {es.threshold}")
    vr = meta.view_region
    if (vr.x, vr.y, vr.w, vr.h) != (0, 0, 1920, 1008):
        r.warn(f, f"view_region {vr.x},{vr.y},{vr.w},{vr.h} differs from the verified 0,0,1920,1008")


def _check_frames(meta: RollMeta, frames: list[FrameRow], r: ValidationReport) -> None:
    f = FILES["frames"]
    if len(frames) != meta.frames:
        r.error(f, f"{len(frames)} rows but roll_meta.frames = {meta.frames}")
    view_h_yd = meta.view_region.h / meta.px_per_cm / YARD_CM
    prev: FrameRow | None = None
    for i, row in enumerate(frames):
        line = i + 2
        if row.frame != i:
            r.error(f, f"frame numbers must be contiguous from 0 (got {row.frame}, expected {i})", line)
            return
        top = row.roll_y_top_px / meta.px_per_cm / YARD_CM
        if not _close(top, row.top_yd, 0.01):
            r.error(f, f"top_yd {row.top_yd} != roll_y_top_px/px_per_cm/91.44 = {top:.4f}", line)
        if not _close(row.bottom_yd - row.top_yd, view_h_yd, 0.02):
            r.warn(f, "bottom_yd - top_yd does not match the view height", line)
        if prev is not None:
            if row.time_s < prev.time_s:
                r.error(f, "time_s decreases", line)
            if row.roll_y_top_px < prev.roll_y_top_px - 1e-6:
                r.warn(f, "fabric moved backwards (roll_y_top_px decreased)", line)
            both_stopped = row.state == "stopped" and prev.state == "stopped"
            if both_stopped and abs(row.roll_y_top_px - prev.roll_y_top_px) > 1.0:
                r.warn(f, "state=stopped but the fabric moved more than 1 px", line)
        prev = row


def _frame_window_px(meta: RollMeta, fr: FrameRow) -> tuple[float, float]:
    return fr.roll_y_top_px, fr.roll_y_top_px + meta.view_region.h


def _check_ground_truth(
    meta: RollMeta,
    frames: list[FrameRow],
    gt: list[GroundTruthRow],
    tax: Taxonomy,
    r: ValidationReport,
) -> None:
    f = FILES["ground_truth"]
    seen: set[str] = set()
    fabric_w_px = meta.fabric_width_cm * meta.px_per_cm
    for i, d in enumerate(gt):
        line = i + 2
        if d.defect_id in seen:
            r.error(f, f"duplicate defect_id {d.defect_id!r}", line)
        seen.add(d.defect_id)
        if not tax.is_known(d.cls):
            r.warn(f, f"class {d.cls!r} not in taxonomy.yaml (maps to other_defect)", line)
        if not (d.start_yd <= d.center_yd <= d.end_yd):
            r.error(f, "start_yd <= center_yd <= end_yd violated", line)
        if not (d.x1_px > d.x0_px and d.y1_px > d.y0_px):
            r.error(f, "degenerate box (x1<=x0 or y1<=y0)", line)
            continue
        # Roll coordinates (verified): y absolute along the roll, x from the fabric's left edge.
        y0_yd = d.y0_px / meta.px_per_cm / YARD_CM
        y1_yd = d.y1_px / meta.px_per_cm / YARD_CM
        if not (_close(y0_yd, d.start_yd, 0.02) and _close(y1_yd, d.end_yd, 0.02)):
            r.error(f, f"y0/y1 ({y0_yd:.3f}/{y1_yd:.3f} yd) disagree with start/end yd", line)
        if d.x0_px < -1 or d.x1_px > fabric_w_px + 1:
            r.error(f, "x0/x1 outside the fabric (x is measured from the fabric's left edge)", line)
        band = meta.selvage_band_px
        if band > 0 and (d.x0_px < band - 1 or d.x1_px > fabric_w_px - band + 1):
            r.warn(f, "box enters the selvage band (simulator clips GT boxes to exclude it)", line)
        w_cm = (d.x1_px - d.x0_px) / meta.px_per_cm
        h_cm = (d.y1_px - d.y0_px) / meta.px_per_cm
        length = max(w_cm, h_cm) / INCH_CM
        if not _close(length, d.length_in, 0.05):
            r.error(f, f"length_in {d.length_in} != max(w_cm, h_cm)/2.54 = {length:.3f}", line)
        cx_cm = (d.x0_px + d.x1_px) / 2 / meta.px_per_cm
        if not _close(cx_cm, d.across_cm, 0.5):
            r.warn(f, f"across_cm {d.across_cm} differs from the box centre {cx_cm:.2f}", line)
        for name in ("first_full_frame", "last_full_frame", "operator_stop_frame"):
            v = getattr(d, name)
            if v is not None and not 0 <= v < len(frames):
                r.error(f, f"{name} {v} outside 0..{len(frames) - 1}", line)
        if d.first_full_frame is not None and d.last_full_frame is not None:
            if d.first_full_frame > d.last_full_frame:
                r.error(f, "first_full_frame > last_full_frame", line)
            else:
                lo, hi = _frame_window_px(meta, frames[d.first_full_frame])
                if not (d.y0_px >= lo - 2 and d.y1_px <= hi + 2):
                    r.warn(f, "box is not fully in view at first_full_frame", line)


def _check_nuisance(meta: RollMeta, frames: list[FrameRow], nuis: list[NuisanceRow], r: ValidationReport) -> None:
    f = FILES["nuisance"]
    for i, n in enumerate(nuis):
        line = i + 2
        if n.appears_frame is not None and not 0 <= n.appears_frame < max(len(frames), 1):
            r.error(f, f"appears_frame {n.appears_frame} outside the video", line)
        if not 0 <= n.center_yd <= meta.roll_length_yd + 0.5:
            r.warn(f, "center_yd outside the roll length", line)
        if not -1 <= n.across_cm <= meta.fabric_width_cm + 1:
            r.warn(f, "across_cm outside the fabric width", line)


def format_report(report: ValidationReport, out: Callable[[str], None] = print) -> None:
    out(f"Dataset: {report.path}")
    for k, v in report.summary.items():
        out(f"  {k}: {v}")
    for e in report.errors:
        out(f"  ERROR   {e}")
    for w in report.warnings:
        out(f"  WARNING {w}")
    out("RESULT: " + ("OK" if report.ok else f"{len(report.errors)} error(s)"))
