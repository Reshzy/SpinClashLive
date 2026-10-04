from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DesktopConfig:
    api_base: str = "http://127.0.0.1:8000"
    keyring_service: str = "color-rush-live"
    request_timeout_s: float = 20.0


def load_config() -> DesktopConfig:
    base = os.environ.get("COLOR_RUSH_API_BASE", "http://127.0.0.1:8000").rstrip("/")
    return DesktopConfig(api_base=base)
