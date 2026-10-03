"""Contract v0 stubs: inspection lifecycle, browser-clocked advance loop, events, verdict, defects.

Implemented in M1 (data model, headless runner) and M2 (live endpoints, SSE). PLAN.md §5, §6.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import Response

from threadeye.api.deps import require
from threadeye.api.errors import NOT_IMPLEMENTED_RESPONSE, not_implemented
from threadeye.api.schemas.events import EventsPage
from threadeye.api.schemas.inspection import (
    AdvanceIn,
    AdvanceOut,
    ConfirmIn,
    DecisionIn,
    DefectOut,
    InspectionCreate,
    InspectionSnapshot,
    LengthIn,
    ManualDefectIn,
    MeasurementIn,
    ReclassifyIn,
    RejectIn,
    SamplingPlanOut,
    ScoreSummary,
    TrackOut,
)
from threadeye.security.rbac import Perm

router = APIRouter(tags=["inspections"], responses=NOT_IMPLEMENTED_RESPONSE)
defects_router = APIRouter(tags=["defects"], responses=NOT_IMPLEMENTED_RESPONSE)

READ = [Depends(require(Perm.INSPECTIONS_READ))]
RUN = [Depends(require(Perm.INSPECTIONS_RUN))]
CONFIRM = [Depends(require(Perm.DEFECTS_CONFIRM))]
IDEMPOTENCY_NOTE = "Send an `Idempotency-Key` header (UUID); retries with the same key are no-ops."


# ------------------------------------------------------------------------------------------ lifecycle
@router.post(
    "/inspections",
    response_model=InspectionSnapshot,
    status_code=status.HTTP_201_CREATED,
    dependencies=RUN,
    description=IDEMPOTENCY_NOTE,
)
def create_inspection(body: InspectionCreate) -> InspectionSnapshot:
    not_implemented("M2")


@router.get("/inspections/{inspection_id}", response_model=InspectionSnapshot, dependencies=READ)
def get_inspection(inspection_id: uuid.UUID) -> InspectionSnapshot:
    not_implemented("M2")


def _lifecycle(action: str) -> None:
    @router.post(
        f"/inspections/{{inspection_id}}/{action}",
        response_model=InspectionSnapshot,
        dependencies=RUN,
        operation_id=f"inspection_{action}",
        description=f"{action.capitalize()} the inspection. {IDEMPOTENCY_NOTE}",
    )
    def endpoint(inspection_id: uuid.UUID) -> InspectionSnapshot:
        not_implemented("M2")


for _action in ("start", "pause", "resume", "complete", "abort"):
    _lifecycle(_action)


@router.get("/inspections/{inspection_id}/plan", response_model=SamplingPlanOut, dependencies=READ)
def sampling_plan(inspection_id: uuid.UUID) -> SamplingPlanOut:
    not_implemented("M2")


@router.get("/inspections/{inspection_id}/track", response_model=TrackOut, dependencies=READ)
def frame_track(inspection_id: uuid.UUID) -> TrackOut:
    not_implemented("M2")


@router.post(
    "/inspections/{inspection_id}/advance",
    response_model=AdvanceOut,
    dependencies=RUN,
    description="Browser-clocked processing of frames (checkpoint, until_frame] in one transaction. "
    "Only the driver-lease holder may call it. " + IDEMPOTENCY_NOTE,
)
def advance(inspection_id: uuid.UUID, body: AdvanceIn) -> AdvanceOut:
    not_implemented("M2")


# ------------------------------------------------------------------------------------------ events
@router.get("/inspections/{inspection_id}/events", response_model=EventsPage, dependencies=READ)
def list_events(
    inspection_id: uuid.UUID,
    after_seq: int = Query(0, ge=0),
    limit: int = Query(500, ge=1, le=2000),
) -> EventsPage:
    not_implemented("M2")


@router.get(
    "/inspections/{inspection_id}/stream",
    response_class=Response,
    dependencies=READ,
    responses={200: {"content": {"text/event-stream": {}}, "description": "SSE (edge profile)"}},
    description="Server-Sent Events. Resume with `Last-Event-ID` (= seq) or `?after_seq=`.",
)
def stream_events(inspection_id: uuid.UUID, after_seq: int = Query(0, ge=0)) -> Response:
    not_implemented("M2")


# ------------------------------------------------------------------------------------------ verdict
@router.get("/inspections/{inspection_id}/score", response_model=ScoreSummary, dependencies=READ)
def get_score(inspection_id: uuid.UUID) -> ScoreSummary:
    not_implemented("M2")


@router.post("/inspections/{inspection_id}/measurements", status_code=201, dependencies=RUN)
def add_measurement(inspection_id: uuid.UUID, body: MeasurementIn) -> None:
    not_implemented("M2")


@router.post("/inspections/{inspection_id}/finalize", response_model=InspectionSnapshot, dependencies=RUN)
def finalize(inspection_id: uuid.UUID) -> InspectionSnapshot:
    not_implemented("M2")


@router.post(
    "/inspections/{inspection_id}/decision",
    response_model=InspectionSnapshot,
    dependencies=[Depends(require(Perm.VERDICT_DECIDE))],
)
def decide(inspection_id: uuid.UUID, body: DecisionIn) -> InspectionSnapshot:
    not_implemented("M2")


# ------------------------------------------------------------------------------------------ defects
@defects_router.get("/inspections/{inspection_id}/defects", response_model=list[DefectOut], dependencies=READ)
def list_defects(inspection_id: uuid.UUID) -> list[DefectOut]:
    not_implemented("M2")


@defects_router.post(
    "/inspections/{inspection_id}/defects",
    response_model=DefectOut,
    status_code=201,
    dependencies=CONFIRM,
    description="Inspector adds a defect the detector missed. " + IDEMPOTENCY_NOTE,
)
def add_manual_defect(inspection_id: uuid.UUID, body: ManualDefectIn) -> DefectOut:
    not_implemented("M2")


@defects_router.get("/defects/{defect_id}", response_model=DefectOut, dependencies=READ)
def get_defect(defect_id: uuid.UUID) -> DefectOut:
    not_implemented("M2")


@defects_router.post("/defects/{defect_id}/confirm", response_model=DefectOut, dependencies=CONFIRM)
def confirm_defect(defect_id: uuid.UUID, body: ConfirmIn) -> DefectOut:
    not_implemented("M2")


@defects_router.post("/defects/{defect_id}/reject", response_model=DefectOut, dependencies=CONFIRM)
def reject_defect(defect_id: uuid.UUID, body: RejectIn) -> DefectOut:
    not_implemented("M2")


@defects_router.post("/defects/{defect_id}/reclassify", response_model=DefectOut, dependencies=CONFIRM)
def reclassify_defect(defect_id: uuid.UUID, body: ReclassifyIn) -> DefectOut:
    not_implemented("M2")


@defects_router.post("/defects/{defect_id}/promote", response_model=DefectOut, dependencies=CONFIRM)
def promote_nondefect(defect_id: uuid.UUID) -> DefectOut:
    not_implemented("M2")


@defects_router.post("/defects/{defect_id}/length", response_model=DefectOut, dependencies=CONFIRM)
def edit_length(defect_id: uuid.UUID, body: LengthIn) -> DefectOut:
    not_implemented("M2")
