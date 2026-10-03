from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from threadeye.api.deps import client_ip, request_id, require
from threadeye.api.schemas.auth import UserCreate, UserOut, UserPatch
from threadeye.db import audit
from threadeye.db.models import User
from threadeye.db.session import get_db
from threadeye.security import sessions
from threadeye.security.passwords import hash_password
from threadeye.security.rbac import DEFAULT_LOCALE, Perm, Role

router = APIRouter(prefix="/users", tags=["admin"])


@router.get("", response_model=list[UserOut])
def list_users(_: User = Depends(require(Perm.USERS_MANAGE)), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.username)))


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    request: Request,
    admin: User = Depends(require(Perm.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> User:
    if db.scalar(select(User.id).where(User.username == body.username)):
        raise HTTPException(status.HTTP_409_CONFLICT, "username already exists")
    user = User(
        username=body.username,
        display_name=body.display_name,
        role=body.role.value,
        password_hash=hash_password(body.password),
        locale=body.locale or DEFAULT_LOCALE[Role(body.role)],
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.create",
        actor_user_id=admin.id,
        actor_role=admin.role,
        entity_type="user",
        entity_id=str(user.id),
        after={"username": user.username, "role": user.role},
        ip=client_ip(request),
        request_id=request_id(request),
    )
    db.commit()
    return user


@router.patch("/{user_id}", response_model=UserOut)
def patch_user(
    user_id: uuid.UUID,
    body: UserPatch,
    request: Request,
    admin: User = Depends(require(Perm.USERS_MANAGE)),
    db: Session = Depends(get_db),
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "user not found")
    changes = body.model_dump(exclude_none=True)
    if "role" in changes:
        changes["role"] = Role(changes["role"]).value
    if user.id == admin.id and (changes.get("active") is False or changes.get("role", user.role) != user.role):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "admins cannot deactivate or demote themselves")
    before = {k: getattr(user, k) for k in changes}
    for k, v in changes.items():
        setattr(user, k, v)
    if changes.get("active") is False:
        sessions.revoke_all_for_user(db, user)
    audit.record(
        db,
        action="user.update",
        actor_user_id=admin.id,
        actor_role=admin.role,
        entity_type="user",
        entity_id=str(user.id),
        before=before,
        after=changes,
        ip=client_ip(request),
        request_id=request_id(request),
    )
    db.commit()
    return user
