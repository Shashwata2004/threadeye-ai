"""Walk every API route with its full path, including routes in included routers.

FastAPI ≥ 0.140 no longer flattens included routers into ``app.routes``, so tests and tooling must
use ``fastapi.routing.iter_route_contexts``. Used by the RBAC matrix and "every route needs a session"
tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, iter_route_contexts

from threadeye.api.deps import PERM_ATTR, current_user
from threadeye.security.rbac import Perm


@dataclass(frozen=True)
class RouteInfo:
    path: str
    methods: frozenset[str]
    dependant: Dependant

    @property
    def perm(self) -> Perm | None:
        stack = list(self.dependant.dependencies)
        while stack:
            dep = stack.pop()
            perm = getattr(dep.call, PERM_ATTR, None)
            if perm is not None:
                return perm  # type: ignore[no-any-return]
            stack.extend(dep.dependencies)
        return None

    @property
    def needs_session(self) -> bool:
        stack = list(self.dependant.dependencies)
        while stack:
            dep = stack.pop()
            if dep.call is current_user or getattr(dep.call, PERM_ATTR, None) is not None:
                return True
            stack.extend(dep.dependencies)
        return False


def iter_api_routes(app: FastAPI) -> Iterator[RouteInfo]:
    for ctx in iter_route_contexts(app.routes):
        route = ctx.original_route
        if isinstance(route, APIRoute):
            yield RouteInfo(
                path=ctx.path or route.path,
                methods=frozenset(ctx.methods or route.methods or ()),
                dependant=route.dependant,
            )
