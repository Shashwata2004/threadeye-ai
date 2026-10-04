"""Runtime settings. Every value comes from environment variables (prefix ``THREADEYE_``)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from threadeye import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="THREADEYE_", extra="ignore")

    deploy_profile: Literal["edge", "cloud_demo"] = "edge"
    database_url: str = "postgresql+psycopg://threadeye:threadeye@localhost:5432/threadeye"
    # Runtime uses the transaction pooler; DDL (migrations) needs a session/direct connection.
    # Empty means "same as database_url" (the edge profile).
    migration_database_url: str = ""

    session_ttl_hours: int = 12
    cookie_secure: bool = False
    allowed_origins: str = ""

    detector_provider: str = "simulated"
    storage_dir: str = "/data/storage"
    datasets_dir: str = "/data/datasets"

    seed_demo_users: bool = False
    seed_sample_data: bool = False
    demo_password: str | None = None

    login_max_failures: int = 10
    login_window_minutes: int = 15

    git_sha: str = "dev"

    @property
    def allowed_origin_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def is_cloud(self) -> bool:
        return self.deploy_profile == "cloud_demo"

    @property
    def ddl_database_url(self) -> str:
        """Connection used for migrations. Supavisor transaction mode cannot run DDL safely."""
        return self.migration_database_url or self.database_url

    @property
    def version(self) -> str:
        return f"{__version__}+{self.git_sha}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
