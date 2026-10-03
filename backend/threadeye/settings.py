"""Runtime settings. Every value comes from environment variables (prefix ``THREADEYE_``)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

from threadeye import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="THREADEYE_", extra="ignore")

    deploy_profile: Literal["edge", "cloud_demo"] = "edge"
    database_url: str = "postgresql+psycopg://threadeye:threadeye@localhost:5432/threadeye"

    session_ttl_hours: int = 12
    cookie_secure: bool = False
    allowed_origins: str = ""

    detector_provider: str = "simulated"
    storage_dir: str = "/data/storage"
    datasets_dir: str = "/data/datasets"

    seed_demo_users: bool = False
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
    def version(self) -> str:
        return f"{__version__}+{self.git_sha}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
