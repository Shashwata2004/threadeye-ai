from __future__ import annotations

from typing import Any, NoReturn

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from threadeye.api.schemas.common import NotImplementedOut


class NotImplementedYet(Exception):
    def __init__(self, milestone: str, what: str = "This endpoint") -> None:
        super().__init__(f"{what} is part of API contract v0 and is implemented in {milestone}")
        self.milestone = milestone


def not_implemented(milestone: str) -> NoReturn:
    raise NotImplementedYet(milestone)


NOT_IMPLEMENTED_RESPONSE: dict[int | str, dict[str, Any]] = {
    501: {"model": NotImplementedOut, "description": "Contract v0: not implemented yet"}
}


def install(app: FastAPI) -> None:
    @app.exception_handler(NotImplementedYet)
    async def _not_implemented(_: Request, exc: NotImplementedYet) -> JSONResponse:
        body = NotImplementedOut(detail=str(exc), planned_milestone=exc.milestone)
        return JSONResponse(status_code=501, content=body.model_dump())
