"""Alembic configuration built in code, so migrations run from an installed package (Docker, CI)."""

from __future__ import annotations

from importlib import resources

from alembic.config import Config

from threadeye.settings import get_settings


def alembic_config(database_url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(resources.files("threadeye.db").joinpath("migrations")))
    cfg.set_main_option("sqlalchemy.url", (database_url or get_settings().database_url).replace("%", "%%"))
    return cfg
