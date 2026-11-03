"""FastAPI application factory. ``uvicorn threadeye.api.app:app``."""

from __future__ import annotations

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from threadeye import __version__
from threadeye.api import errors
from threadeye.api.middleware import OriginCheckMiddleware, RequestIdMiddleware
from threadeye.api.routers import auth, health, inspections, operations, receiving, system, users
from threadeye.settings import get_settings

API_PREFIX = "/api/v1"

DESCRIPTION = """
ThreadEye AI: fabric inspection assistant. Core inspection and M4–M6 operational features.

Endpoints that return **501** are part of the agreed contract and are implemented in the milestone
named in the response (`planned_milestone`). Every mutating endpoint is permission-checked
server-side and writes an append-only audit row.

All demonstration video is simulated. The answer-key-based simulated detector is not AI;
the local YOLOX-S provider runs trained-model inference. Mode and provider are disclosed separately.
Verification checks reference-video pipeline behaviour, not physical camera calibration.
"""


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(
        title="ThreadEye AI API",
        version=__version__,
        description=DESCRIPTION,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
    )
    errors.install(app)

    app.add_middleware(OriginCheckMiddleware, allowed=s.allowed_origin_list)
    if s.allowed_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.allowed_origin_list,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "Idempotency-Key", "Last-Event-ID", "X-Request-ID"],
        )
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router)
    v1 = APIRouter(prefix=API_PREFIX)
    for r in (
        auth.router,
        users.router,
        operations.router,
        system.router,
        receiving.router,
        inspections.datasets_router,
        inspections.router,
        inspections.defects_router,
    ):
        v1.include_router(r)
    app.include_router(v1)
    return app


app = create_app()
