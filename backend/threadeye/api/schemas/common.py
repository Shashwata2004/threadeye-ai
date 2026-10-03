from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorOut(ApiModel):
    detail: str


class NotImplementedOut(ApiModel):
    """Returned (HTTP 501) by contract-v0 endpoints that are not built yet."""

    detail: str
    planned_milestone: str
