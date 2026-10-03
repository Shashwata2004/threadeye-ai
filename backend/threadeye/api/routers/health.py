"""``GET /health`` at the API root (outside /api/v1).

Unauthenticated and runs a trivial DB query (``SELECT 1``). Used by the Docker healthcheck and by
the daily GitHub Actions keep-alive, so the Supabase free project never pauses during judging.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from threadeye.api.schemas.system import HealthOut
from threadeye.db.session import ping
from threadeye.settings import get_settings

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthOut,
    responses={503: {"model": HealthOut, "description": "Database unreachable"}},
)
def health() -> JSONResponse:
    s = get_settings()
    try:
        db_ok = ping()
    except Exception:  # never leak connection details
        db_ok = False
    body = HealthOut(
        status="ok" if db_ok else "error",
        db="ok" if db_ok else "error",
        profile=s.deploy_profile,
        version=s.version,
        simulated_mode=True,  # only the simulated provider exists in this phase
    )
    return JSONResponse(status_code=200 if db_ok else 503, content=body.model_dump())
