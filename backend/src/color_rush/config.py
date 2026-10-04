from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    color_rush_env: Literal["production", "simulation"] = "simulation"
    database_url: str = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5432/color_rush_sim"
    redis_url: str = "redis://127.0.0.1:6379/0"
    color_rush_host: str = "127.0.0.1"
    color_rush_port: int = 8000
    color_rush_worker_role: Literal["coordinator", "settlement", "all"] = "all"
    color_rush_worker_id: str = "local-worker-1"
    coordinator_lease_ttl_seconds: int = 15
    settlement_partition_count: int = 8
    drain_poll_interval_ms: int = 50
    secret_key: str = "change-me-dev-only"
    color_rush_timezone: str = "Asia/Manila"

    @property
    def is_simulation(self) -> bool:
        return self.color_rush_env == "simulation"


@lru_cache
def get_settings() -> Settings:
    return Settings()
