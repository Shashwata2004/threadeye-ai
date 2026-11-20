from __future__ import annotations

import hashlib
import platform
from datetime import UTC, datetime, timedelta
from importlib.metadata import version

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from threadeye.api.deps import require
from threadeye.api.introspect import iter_api_routes
from threadeye.api.schemas.docs import DocsConfig, DocsDocument, DocsLive
from threadeye.db.audit import record
from threadeye.db.models import AuditLog, ComponentHeartbeat, Inspection, Roll, Setting, User
from threadeye.db.session import get_db
from threadeye.security.rbac import Perm
from threadeye.services.docs_content import default_config
from threadeye.services.provider_config import current_provider
from threadeye.settings import get_settings

router = APIRouter(prefix="/documentation", tags=["documentation"])
KEY = "public_docs_v1"
NO_CACHE = {"Cache-Control": "no-store, max-age=0", "Pragma": "no-cache"}


def config(db: Session) -> DocsConfig:
    row = db.get(Setting, KEY)
    return DocsConfig.model_validate(row.value) if row else default_config()


def visible(body: DocsConfig, now: datetime) -> bool:
    return (
        body.enabled
        and (body.starts_at is None or now >= body.starts_at)
        and (body.ends_at is None or now < body.ends_at)
    )


def document(db: Session, request: Request, body: DocsConfig) -> DocsDocument:
    now = datetime.now(UTC)
    live = None
    if body.show_live:

        def count(model: type, *conditions: ColumnElement[bool]) -> int:
            q = select(func.count()).select_from(model)
            if conditions:
                q = q.where(*conditions)
            return int(db.scalar(q) or 0)

        heartbeat = db.get(ComponentHeartbeat, "worker")
        provider = current_provider(db)
        live = DocsLive(
            generated_at=now,
            version=get_settings().version,
            profile=get_settings().deploy_profile,
            worker_alive=bool(heartbeat and now - heartbeat.last_seen_at < timedelta(seconds=30)),
            active_provider=provider,
            detector_is_simulated=provider == "simulated",
            registered_rolls=count(Roll),
            inspections=count(Inspection),
            finalized_inspections=count(Inspection, Inspection.finalized_at.is_not(None)),
            simulated_video_inspections=count(Inspection, Inspection.is_simulated.is_(True)),
            active_users=count(User, User.active.is_(True)),
            audit_events=count(AuditLog),
            verdicts={
                str(k): int(v)
                for k, v in db.execute(
                    select(Inspection.system_verdict, func.count())
                    .where(Inspection.finalized_at.is_not(None))
                    .group_by(Inspection.system_verdict)
                )
                if k
            },
            runtime={
                "Python": platform.python_version(),
                "FastAPI": version("fastapi"),
                "SQLAlchemy": version("sqlalchemy"),
            },
        )
    apis = (
        [
            {
                "path": r.path,
                "methods": sorted(r.methods),
                "access": r.perm.value if r.perm else "session" if r.needs_session else "public",
            }
            for r in iter_api_routes(request.app)
        ]
        if body.show_apis
        else []
    )
    return DocsDocument(content=body, live=live, apis=apis)


@router.get("", response_model=DocsDocument)
def public(request: Request, response: Response, db: Session = Depends(get_db)) -> DocsDocument:
    response.headers.update(NO_CACHE)
    body = config(db)
    if not visible(body, datetime.now(UTC)):
        raise HTTPException(404, "Documentation is not currently published", headers=NO_CACHE)
    body = body.model_copy(
        update={
            "sections": [section for section in body.sections if section.visible],
            "members": body.members if body.show_team else [],
        }
    )
    return document(db, request, body)


@router.get("/admin", response_model=DocsConfig)
def admin_read(
    response: Response, _: User = Depends(require(Perm.SETTINGS_MANAGE)), db: Session = Depends(get_db)
) -> DocsConfig:
    response.headers.update(NO_CACHE)
    return config(db)


@router.get("/preview", response_model=DocsDocument)
def preview(
    request: Request,
    response: Response,
    _: User = Depends(require(Perm.SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
) -> DocsDocument:
    response.headers.update(NO_CACHE)
    return document(db, request, config(db))


@router.put("/admin", response_model=DocsConfig)
def save(
    body: DocsConfig,
    response: Response,
    actor: User = Depends(require(Perm.SETTINGS_MANAGE)),
    db: Session = Depends(get_db),
) -> DocsConfig:
    response.headers.update(NO_CACHE)
    db.execute(text("SELECT pg_advisory_xact_lock(81247891)"))
    previous = config(db)
    if body.revision != previous.revision:
        raise HTTPException(409, "Documentation changed; reload before saving")
    body.revision += 1
    value = body.model_dump(mode="json")
    row = db.get(Setting, KEY)
    if row is None:
        row = Setting(key=KEY, value=value, updated_by=actor.id)
        db.add(row)
    else:
        row.value, row.updated_by = value, actor.id
    record(
        db,
        action="docs.update",
        actor_user_id=actor.id,
        actor_role=actor.role,
        entity_type="documentation",
        entity_id=KEY,
        after={
            "revision": body.revision,
            "enabled": body.enabled,
            "sha256": hashlib.sha256(body.model_dump_json().encode()).hexdigest(),
        },
    )
    db.commit()
    return body
