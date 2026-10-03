"""Contract v0 stubs: master data, lots, rolls, QR labels. Implemented in M1 (owner A).

Each endpoint already has its final path, schema and permission check, so the frontend can build
against the OpenAPI contract (with MSW mocks) while the backend fills in the logic.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response

from threadeye.api.deps import require
from threadeye.api.errors import NOT_IMPLEMENTED_RESPONSE, not_implemented
from threadeye.api.schemas.receiving import (
    BuyerOut,
    LotCreate,
    LotOut,
    MachineOut,
    RollOut,
    RollsBulkCreate,
    RuleProfileSummary,
    SamplingSuggestionOut,
    SupplierIn,
    SupplierOut,
)
from threadeye.security.rbac import Perm

router = APIRouter(tags=["receiving"], responses=NOT_IMPLEMENTED_RESPONSE)
M = "M1"
PDF: dict[int | str, dict[str, Any]] = {200: {"content": {"application/pdf": {}}, "description": "PDF document"}}


@router.get("/suppliers", response_model=list[SupplierOut], dependencies=[Depends(require(Perm.MASTER_DATA_READ))])
def list_suppliers() -> list[SupplierOut]:
    not_implemented(M)


@router.post(
    "/suppliers",
    response_model=SupplierOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Perm.MASTER_DATA_WRITE))],
)
def create_supplier(body: SupplierIn) -> SupplierOut:
    not_implemented(M)


@router.get("/buyers", response_model=list[BuyerOut], dependencies=[Depends(require(Perm.MASTER_DATA_READ))])
def list_buyers() -> list[BuyerOut]:
    not_implemented(M)


@router.get("/machines", response_model=list[MachineOut], dependencies=[Depends(require(Perm.MASTER_DATA_READ))])
def list_machines() -> list[MachineOut]:
    not_implemented(M)


@router.get(
    "/rule-profiles", response_model=list[RuleProfileSummary], dependencies=[Depends(require(Perm.PROFILES_READ))]
)
def list_rule_profiles(buyer_id: uuid.UUID | None = None) -> list[RuleProfileSummary]:
    not_implemented(M)


@router.get("/lots", response_model=list[LotOut], dependencies=[Depends(require(Perm.LOTS_READ))])
def list_lots() -> list[LotOut]:
    not_implemented(M)


@router.post(
    "/lots",
    response_model=LotOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Perm.LOTS_WRITE))],
)
def create_lot(body: LotCreate) -> LotOut:
    not_implemented(M)


@router.get("/lots/{lot_id}", response_model=LotOut, dependencies=[Depends(require(Perm.LOTS_READ))])
def get_lot(lot_id: uuid.UUID) -> LotOut:
    not_implemented(M)


@router.post(
    "/lots/{lot_id}/rolls",
    response_model=list[RollOut],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Perm.ROLLS_WRITE))],
)
def add_rolls(lot_id: uuid.UUID, body: RollsBulkCreate) -> list[RollOut]:
    not_implemented(M)


@router.get(
    "/lots/{lot_id}/sampling-suggestion",
    response_model=SamplingSuggestionOut,
    dependencies=[Depends(require(Perm.LOTS_READ))],
)
def sampling_suggestion(lot_id: uuid.UUID) -> SamplingSuggestionOut:
    not_implemented(M)


@router.get(
    "/lots/{lot_id}/labels.pdf",
    response_class=Response,
    responses=PDF,
    dependencies=[Depends(require(Perm.LABELS_PRINT))],
)
def lot_labels_pdf(lot_id: uuid.UUID) -> Response:
    not_implemented(M)


@router.get("/rolls", response_model=list[RollOut], dependencies=[Depends(require(Perm.ROLLS_READ))])
def list_rolls(lot_id: uuid.UUID | None = None, status_filter: str | None = None) -> list[RollOut]:
    not_implemented(M)


@router.get("/rolls/by-code/{roll_code}", response_model=RollOut, dependencies=[Depends(require(Perm.ROLLS_READ))])
def roll_by_code(roll_code: str) -> RollOut:
    not_implemented(M)


@router.get("/rolls/{roll_id}", response_model=RollOut, dependencies=[Depends(require(Perm.ROLLS_READ))])
def get_roll(roll_id: uuid.UUID) -> RollOut:
    not_implemented(M)


@router.get(
    "/rolls/{roll_id}/label.pdf",
    response_class=Response,
    responses=PDF,
    dependencies=[Depends(require(Perm.LABELS_PRINT))],
)
def roll_label_pdf(roll_id: uuid.UUID) -> Response:
    not_implemented(M)
