"""Durable evaluation jobs. Answer keys are read only by the benchmark service."""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text

from threadeye.db import audit
from threadeye.db.models import DefectRow, Inspection, Machine, OperationRun, Setting, User
from threadeye.db.session import get_sessionmaker
from threadeye.providers.simulated import PRESETS
from threadeye.security.rbac import Perm, has_perm
from threadeye.services import benchmark, datasets, live, storage
from threadeye.settings import get_settings

log = logging.getLogger(__name__)


def schedule_daily() -> None:
    """Once per Dhaka day per configured machine; no unrequested factory/model defaults."""
    today = datetime.now(ZoneInfo("Asia/Dhaka")).date()
    midnight = datetime.combine(today, time.min, tzinfo=ZoneInfo("Asia/Dhaka"))
    with get_sessionmaker()() as db:
        for row in db.scalars(select(Setting).where(Setting.key.like("verification:%"))):
            payload = dict(row.value)
            if not payload.get("enabled") or not row.updated_by:
                continue
            actor = db.get(User, row.updated_by)
            if not actor or not actor.active or not has_perm(actor.role, Perm.VERIFICATION_RUN):
                continue
            machine_id = uuid.UUID(payload["machine_id"])
            machine = db.get(Machine, machine_id)
            if not machine or not machine.active:
                continue
            db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": row.key})
            exists = db.scalar(
                select(OperationRun.id)
                .where(
                    OperationRun.kind == "verification",
                    OperationRun.machine_id == machine_id,
                    OperationRun.created_at >= midnight,
                )
                .limit(1)
            )
            if exists:
                continue
            db.add(
                OperationRun(
                    kind="verification", status="queued", actor_id=actor.id, machine_id=machine_id, inputs=payload
                )
            )
        db.commit()


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_inputs(inputs: dict[str, Any], *, benchmark_run: bool) -> None:
    settings = get_settings()
    if inputs["provider_id"] == "local_model":
        if settings.is_serverless:
            raise ValueError("real-model evaluation runs on the edge laptop; cloud demo supports simulation")
        live._local_model_config()
    for dataset_id in inputs["dataset_ids"]:
        info = datasets.get_dataset(dataset_id)
        if benchmark_run:
            manifest_path = info.path / "evaluation_manifest.json"
            if not manifest_path.exists():
                raise ValueError(f"{dataset_id}: a held-out test manifest is required for benchmarking")
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("split") != "test" or manifest.get("training_excluded") is not True:
                raise ValueError(f"{dataset_id}: benchmarking refuses train/validation or unverified data")


def execute(run_id: uuid.UUID) -> bool:
    """Claim with SKIP LOCKED; an abandoned lease can be retried after ten minutes."""
    with get_sessionmaker()() as db:
        run = db.scalar(select(OperationRun).where(OperationRun.id == run_id).with_for_update(skip_locked=True))
        if run is None or run.status in {"completed", "failed"}:
            return False
        if run.status == "running" and run.started_at and run.started_at > datetime.now(UTC) - timedelta(minutes=10):
            return False
        run.status, run.started_at = "running", datetime.now(UTC)
        kind, inputs, inspection_id = run.kind, dict(run.inputs), run.inspection_id
        db.commit()
    try:
        result = clip(run_id, inspection_id, inputs) if kind == "clip" else evaluate(inputs, kind)
        error = None
    except Exception:
        log.exception("operation %s failed", run_id)
        result, error = None, "Run failed. Check local worker logs and dataset/model availability."
    with get_sessionmaker()() as db:
        run = db.get(OperationRun, run_id)
        assert run
        run.result, run.error = result, error
        run.status, run.completed_at = ("failed" if error else "completed"), datetime.now(UTC)
        actor = db.get(User, run.actor_id)
        audit.record(
            db,
            action=f"{run.kind}.completed",
            actor_user_id=run.actor_id,
            actor_role=actor.role if actor else None,
            entity_type="operation_run",
            entity_id=str(run.id),
            after={"status": run.status, "passed": (result or {}).get("passed")},
        )
        db.commit()
    return True


def work_once() -> bool:
    with get_sessionmaker()() as db:
        run_id = db.scalar(
            select(OperationRun.id)
            .where(
                or_(
                    OperationRun.status == "queued",
                    (OperationRun.status == "running")
                    & (OperationRun.started_at < datetime.now(UTC) - timedelta(minutes=10)),
                )
            )
            .order_by(OperationRun.created_at)
            .limit(1)
        )
    return execute(run_id) if run_id else False


def evaluate(inputs: dict[str, Any], kind: str) -> dict[str, Any]:
    validate_inputs(inputs, benchmark_run=kind == "benchmark")
    reports = []
    for dataset_id in inputs["dataset_ids"]:
        info = datasets.get_dataset(dataset_id)
        config = inputs.get("provider_config") or (
            live._local_model_config() if inputs["provider_id"] == "local_model" else None
        )
        started = perf_counter()
        output = benchmark.run_roll(
            info.path,
            preset={**PRESETS[inputs["preset"]], "seed": inputs.get("seed", 42)},
            provider_id=inputs["provider_id"],
            provider_config=config,
        )
        delta = abs(output.score.per_100 - output.truth_score.per_100)
        ev = output.evaluation
        reasons = []
        if ev.recall < inputs["min_recall"]:
            reasons.append("recall_below_tolerance")
        if ev.fp > inputs["max_false_alarms"]:
            reasons.append("false_alarms_above_tolerance")
        if delta > inputs["max_score_delta"]:
            reasons.append("score_delta_above_tolerance")
        raw = sum(
            len(event.payload.get("detections", [])) for event in output.events if event.type == "detection.batch"
        )
        files = {
            name: digest(info.path / name)
            for name in ("roll_meta.json", "frames.csv", "ground_truth.csv", "nuisance.csv")
        }
        if info.video_path:
            files[info.video_path.name] = digest(info.video_path)
        if config:
            files["model"] = digest(Path(config["model_path"]))
            files["model_info.json"] = digest(
                Path(config.get("info_path") or Path(config["model_path"]).with_name("model_info.json"))
            )
        reports.append(
            {
                "dataset_id": dataset_id,
                "simulated_video": True,
                "simulated_detections": inputs["provider_id"] == "simulated",
                "provider": output.provider_label,
                "evaluation": ev.as_dict(),
                "coverage_pct": output.coverage_pct,
                "seconds": round(perf_counter() - started, 3),
                "points": output.score.total_points,
                "per_100": round(output.score.per_100, 2),
                "verdict": output.score.verdict,
                "truth_points": output.truth_score.total_points,
                "truth_per_100": round(output.truth_score.per_100, 2),
                "truth_verdict": output.truth_score.verdict,
                "score_delta": round(delta, 3),
                "passed": not reasons,
                "reasons": reasons,
                "sha256": files,
                "funnel": {
                    "raw_mapped": raw,
                    "deduplicated": len(output.defects),
                    "filtered_nondefects": sum(d["kind"] != "defect" for d in output.defects),
                    "remaining_defects": sum(d["kind"] == "defect" for d in output.defects),
                },
            }
        )
    return {
        "passed": all(r["passed"] for r in reports),
        "rolls": reports,
        "scope": "reference-video pipeline check; not physical camera calibration or factory impact",
    }


def clip(run_id: uuid.UUID, inspection_id: uuid.UUID | None, inputs: dict[str, Any]) -> dict[str, Any]:
    executable = shutil.which("ffmpeg")
    if not executable or inspection_id is None:
        raise ValueError("ffmpeg and an inspection are required")
    with get_sessionmaker()() as db:
        inspection = db.get(Inspection, inspection_id)
        defect = db.get(DefectRow, uuid.UUID(inputs["defect_id"]))
        if not inspection or not inspection.dataset_id or not defect or defect.inspection_id != inspection_id:
            raise ValueError("defect not in inspection")
        info = datasets.get_dataset(inspection.dataset_id)
        if not info.video_path:
            raise ValueError("local video required for MP4 export")
        start = max(0, (defect.first_frame or defect.best_frame) / info.fps - 1.5)
        end = min(info.frames / info.fps, (defect.last_frame or defect.best_frame) / info.fps + 1.5)
        with tempfile.TemporaryDirectory(prefix="threadeye-clip-") as directory:
            output = Path(directory) / "clip.mp4"
            subprocess.run(  # noqa: S603 -- local executable and argument list; no shell
                [
                    executable,
                    "-nostdin",
                    "-v",
                    "error",
                    "-ss",
                    str(start),
                    "-i",
                    str(info.video_path),
                    "-t",
                    str(max(end - start, 0.2)),
                    "-an",
                    "-c:v",
                    "libx264",
                    "-preset",
                    "fast",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(output),
                ],
                check=True,
                capture_output=True,
                timeout=120,
            )
            key = f"clips/{run_id}.mp4"
            sha = storage.put(db, key, output.read_bytes(), "video/mp4")
            db.commit()
        return {
            "storage_key": key,
            "sha256": sha,
            "start_s": start,
            "end_s": end,
            "simulated_video": inspection.is_simulated,
        }
