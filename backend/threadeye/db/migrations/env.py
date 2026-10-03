from __future__ import annotations

from typing import Any

from alembic import context
from sqlalchemy import create_engine, pool, text

from threadeye.db import models  # noqa: F401  (registers tables on Base.metadata)
from threadeye.db.base import SCHEMA, Base
from threadeye.settings import get_settings

config = context.config
target_metadata = Base.metadata


def _only_our_schema(name: str | None, type_: str, _parent: Any) -> bool:
    return type_ != "schema" or name == SCHEMA


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url") or get_settings().database_url
    # Pin the default schema to public at connect time. Postgres's default search_path
    # ("$user", public) would otherwise make "threadeye" the default schema whenever the DB user is
    # also named "threadeye", and autogenerate would mis-compare the schema-qualified tables.
    # (SQLAlchemy caches the default schema on first connect, so a later SET is too late.)
    engine = create_engine(url, poolclass=pool.NullPool, connect_args={"options": "-csearch_path=public"})
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_schemas=True,
            include_name=_only_our_schema,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    """Emit the migrations as SQL instead of running them.

    Used by ``threadeye migrate --sql``, so the schema can be created through Supabase's
    Management API (``supabase db query``), which needs no database password.
    """
    print(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}";')
    context.configure(
        url=config.get_main_option("sqlalchemy.url") or get_settings().ddl_database_url,
        target_metadata=target_metadata,
        version_table_schema=SCHEMA,
        include_schemas=True,
        include_name=_only_our_schema,
        compare_type=True,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
