"""Persist the default for NEW inspections; existing inspections retain their pinned provider."""

from sqlalchemy.orm import Session

from threadeye.db.models import Setting
from threadeye.settings import get_settings


def provider_key() -> str:
    return "detector_provider:serverless" if get_settings().is_serverless else "detector_provider:edge"


def current_provider(db: Session) -> str:
    row = db.get(Setting, provider_key())
    return str(row.value) if row and row.value in {"simulated", "local_model"} else get_settings().detector_provider
