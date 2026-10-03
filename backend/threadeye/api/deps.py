"""Request dependencies: DB session, current user, server-side permission checks."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from threadeye.db.models import User
from threadeye.db.session import get_db
from threadeye.security import sessions
from threadeye.security.rbac import Perm, has_perm

PERM_ATTR = "__threadeye_perm__"


def client_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def current_user_optional(request: Request, db: Session = Depends(get_db)) -> User | None:
    return sessions.resolve(db, request.cookies.get(sessions.COOKIE_NAME))


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    return user


def require(perm: Perm) -> Callable[..., User]:
    """``Depends(require(Perm.X))``: 401 if not logged in, 403 if the role lacks ``perm``."""

    def dependency(user: User = Depends(current_user)) -> User:
        if not has_perm(user.role, perm):
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"missing permission: {perm.value}")
        return user

    setattr(dependency, PERM_ATTR, perm)  # lets the RBAC matrix test discover every guarded route
    return dependency
