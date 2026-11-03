"""``GET /health`` at the API root (outside /api/v1).

Unauthenticated and runs a trivial DB query (``SELECT 1``). Used by the Docker healthcheck and by
the daily GitHub Actions keep-alive, so the Supabase free project never pauses during judging.
"""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from threadeye.api.schemas.system import HealthOut
from threadeye.db.session import get_db, ping
from threadeye.providers.registry import REGISTRY
from threadeye.services.provider_config import current_provider
from threadeye.settings import get_settings

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthOut,
    responses={503: {"model": HealthOut, "description": "Database unreachable"}},
)
def health(db: Session = Depends(get_db)) -> JSONResponse:
    s = get_settings()
    try:
        db_ok = ping()
    except Exception:  # never leak connection details
        db_ok = False
    provider_id = current_provider(db) if db_ok else s.detector_provider
    body = HealthOut(
        status="ok" if db_ok else "error",
        db="ok" if db_ok else "error",
        profile=s.deploy_profile,
        version=s.version,
        simulated_mode=REGISTRY.get(provider_id, REGISTRY["simulated"]).is_simulated,
    )
    return JSONResponse(status_code=200 if db_ok else 503, content=body.model_dump())
