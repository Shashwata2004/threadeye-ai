"""Contract v0: receiving (master data, lots, rolls). Implemented in M1."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from threadeye.api.schemas.common import ApiModel

RollStatus = Literal["registered", "in_inspection", "inspected", "on_hold", "released", "returned"]
LotVerdict = Literal["PENDING_SAMPLE", "ACCEPT", "HOLD_INSPECT_ALL", "ACCEPT_WITH_REJECTS", "REJECT"]


class NamedRef(ApiModel):
    id: uuid.UUID
    name: str
    is_sample_data: bool = False


class SupplierIn(ApiModel):
    name: str = Field(min_length=1, max_length=128)
    country: str | None = Field(default=None, max_length=64)


class SupplierOut(NamedRef):
    country: str | None


class BuyerOut(NamedRef):
    pass


class MachineOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    active: bool


class RuleProfileSummary(ApiModel):
    id: uuid.UUID
    buyer_id: uuid.UUID | None
    name: str
    version: int
    status: Literal["draft", "active", "retired"]
    threshold_per_100: float


class LotCreate(ApiModel):
    challan_no: str = Field(min_length=1, max_length=64)
    supplier_id: uuid.UUID
    buyer_id: uuid.UUID
    order_ref: str | None = Field(default=None, max_length=64)
    fabric_type: str = Field(min_length=1, max_length=128)
    colour: str | None = Field(default=None, max_length=64)
    received_at: date
    declared_rolls: int = Field(ge=1, le=10_000)
    declared_total_yd: float | None = Field(default=None, gt=0)
    rule_profile_id: uuid.UUID | None = None
    sampling_pct: float | None = Field(default=None, gt=0, le=100)


class LotOut(ApiModel):
    id: uuid.UUID
    challan_no: str
    supplier: NamedRef
    buyer: NamedRef
    order_ref: str | None
    fabric_type: str
    colour: str | None
    received_at: date
    declared_rolls: int
    declared_total_yd: float | None
    rule_profile: RuleProfileSummary | None
    sampling_pct: float
    status: str
    lot_verdict: LotVerdict | None
    rolls_registered: int
    is_sample_data: bool
    created_at: datetime


class RollCreate(ApiModel):
    mill_roll_no: str = Field(min_length=1, max_length=64)
    dye_lot: str | None = Field(default=None, max_length=64)
    declared_length_yd: float = Field(gt=0, le=2000)
    declared_width_in: float = Field(gt=0, le=200)
    gsm: float | None = Field(default=None, gt=0)


class RollsBulkCreate(ApiModel):
    rolls: list[RollCreate] = Field(min_length=1, max_length=1000)


class RollOut(ApiModel):
    id: uuid.UUID
    lot_id: uuid.UUID
    roll_code: str
    mill_roll_no: str
    dye_lot: str | None
    declared_length_yd: float
    declared_width_in: float
    gsm: float | None
    status: RollStatus
    selected_for_inspection: bool
    label_printed_at: datetime | None
    is_sample_data: bool


class SamplingSuggestionOut(ApiModel):
    total_rolls: int
    registered_rolls: int
    suggested_count: int
    sampling_pct: float
    basis: Literal["profile"]
    mill_recent_fail_rate: float | None
    mill_recent_rolls: int
