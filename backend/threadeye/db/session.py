"""Engine and session factory.

edge:       normal connection pool against the local Postgres.
cloud_demo: Supabase transaction pooler → no server-side prepared statements (PLAN.md §12:
            Supavisor transaction mode does not support them). A long-running API (`make cloud-run`)
            keeps a few connections open: a new TLS connection to Supabase costs over a second from
            Bangladesh. Serverless functions (Vercel) use NullPool, as a frozen function cannot keep one.
"""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from threadeye.settings import get_settings


def make_engine(url: str, *, cloud: bool, serverless: bool = False) -> Engine:
    kwargs: dict[str, Any] = {}
    if cloud:
        kwargs |= {"connect_args": {"prepare_threshold": None}}
        if serverless:
            kwargs |= {"poolclass": NullPool}
        else:
            # No pre-ping: it would cost a round trip per request. Connections are renewed every 2 min.
            kwargs |= {"pool_size": 3, "max_overflow": 3, "pool_recycle": 120}
    else:
        kwargs |= {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5}
    return create_engine(url, **kwargs)


@lru_cache
def get_engine() -> Engine:
    s = get_settings()
    return make_engine(s.database_url, cloud=s.is_cloud, serverless=s.is_serverless)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency. Endpoints commit explicitly; anything uncommitted is rolled back."""
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()


def ping(engine: Engine | None = None) -> bool:
    with (engine or get_engine()).connect() as conn:
        return bool(conn.execute(text("SELECT 1")).scalar_one() == 1)
