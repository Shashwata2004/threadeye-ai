from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from threadeye.api.deps import client_ip, current_user, request_id
from threadeye.api.schemas.auth import LoginIn, MeOut, MePatch
from threadeye.db import audit
from threadeye.db.models import AuditLog, User
from threadeye.db.session import get_db
from threadeye.security import sessions
from threadeye.security.passwords import DUMMY_HASH, hash_password, needs_rehash, verify_password
from threadeye.security.rbac import perms_for
from threadeye.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])


def me_out(user: User) -> MeOut:
    return MeOut.model_validate(
        {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "locale": user.locale,
            "digit_style": user.digit_style,
            "permissions": perms_for(user.role),
        }
    )


@router.post(
    "/login",
    response_model=MeOut,
    responses={401: {"description": "Invalid credentials"}, 429: {"description": "Too many failures"}},
)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> MeOut:
    s = get_settings()
    username = body.username.strip().lower()
    since = datetime.now(UTC) - timedelta(minutes=s.login_window_minutes)
    failures = db.scalar(
        select(func.count())
        .select_from(AuditLog)
        .where(AuditLog.action == "auth.login_failed", AuditLog.entity_id == username, AuditLog.at >= since)
    )
    if (failures or 0) >= s.login_max_failures:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many failed attempts; try later")

    user = db.scalar(select(User).where(User.username == username))
    ok = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if user is None or not user.active or not ok:
        audit.record(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=username,
            ip=client_ip(request),
            request_id=request_id(request),
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid username or password")

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
    token = sessions.create_session(
        db,
        user,
        ttl_hours=s.session_ttl_hours,
        ip=client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    user.last_login_at = datetime.now(UTC)
    audit.record(
        db,
        action="auth.login",
        actor_user_id=user.id,
        actor_role=user.role,
        entity_type="user",
        entity_id=str(user.id),
        ip=client_ip(request),
        request_id=request_id(request),
    )
    db.commit()
    response.set_cookie(
        sessions.COOKIE_NAME,
        token,
        max_age=s.session_ttl_hours * 3600,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    return me_out(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)) -> Response:
    sessions.revoke(db, request.cookies.get(sessions.COOKIE_NAME))
    audit.record(
        db,
        action="auth.logout",
        actor_user_id=user.id,
        actor_role=user.role,
        entity_type="user",
        entity_id=str(user.id),
        ip=client_ip(request),
        request_id=request_id(request),
    )
    db.commit()
    out = Response(status_code=status.HTTP_204_NO_CONTENT)
    out.delete_cookie(sessions.COOKIE_NAME, path="/")
    return out


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(current_user)) -> MeOut:
    return me_out(user)


@router.patch("/me", response_model=MeOut)
def patch_me(
    body: MePatch, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> MeOut:
    changes = body.model_dump(exclude_none=True)
    if changes:
        before = {k: getattr(user, k) for k in changes}
        for k, v in changes.items():
            setattr(user, k, v)
        audit.record(
            db,
            action="user.update_self",
            actor_user_id=user.id,
            actor_role=user.role,
            entity_type="user",
            entity_id=str(user.id),
            before=before,
            after=changes,
            ip=client_ip(request),
            request_id=request_id(request),
        )
        db.commit()
    return me_out(user)
