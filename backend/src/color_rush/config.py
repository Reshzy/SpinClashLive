from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

WorkerRoleName = Literal[
    "coordinator",
    "ingest",
    "settlement",
    "outbox",
    "projection",
    "gateway",
    "retention",
    "all",
]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    color_rush_env: Literal["production", "simulation"] = "simulation"
    database_url: str = "postgresql+psycopg://color_rush:color_rush@127.0.0.1:5432/color_rush_sim"
    redis_url: str = "redis://127.0.0.1:6379/0"
    color_rush_host: str = "127.0.0.1"
    color_rush_port: int = 8000
    color_rush_worker_role: WorkerRoleName = "all"
    color_rush_worker_id: str = "local-worker-1"
    coordinator_lease_ttl_seconds: int = 15
    settlement_partition_count: int = 8
    drain_poll_interval_ms: int = 50
    secret_key: str = "change-me-dev-only"
    color_rush_timezone: str = "Asia/Manila"
    cors_origins: str = (
        "http://127.0.0.1:8000,http://localhost:8000,"
        "http://127.0.0.1:5173,http://localhost:5173"
    )
    jwt_access_ttl_seconds: int = 900
    jwt_refresh_ttl_seconds: int = 60 * 60 * 24 * 7
    overlay_ticket_ttl_seconds: int = 60 * 60 * 24 * 30
    overlay_ws_ticket_ttl_seconds: int = 120
    snapshot_hz: float = 4.0
    command_retention_days: int = 7
    source_lag_pause_ms: int = 8000
    source_backlog_pause: int = 2000
    youtube_transport: Literal["stream", "poll"] = "stream"
    google_api_key: str | None = None
    google_oauth_client_id: str | None = None
    google_oauth_client_secret: str | None = None
    google_oauth_redirect_uri: str = "http://127.0.0.1:8000/api/v1/admin/youtube/oauth/callback"
    bootstrap_owner_username: str = "owner"
    bootstrap_owner_password: str = "change-me-owner"
    trusted_metrics: bool = False

    @property
    def is_simulation(self) -> bool:
        return self.color_rush_env == "simulation"

    @property
    def origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
