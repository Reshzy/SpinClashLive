"""Structured logging helpers and metrics."""

from __future__ import annotations

import logging
from collections.abc import MutableMapping
from typing import Any

import structlog

REDACT_KEYS = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "secret_key",
        "authorization",
        "api_key",
        "google_api_key",
        "client_secret",
        "overlay_secret",
        "ticket",
    }
)


def _redact_value(key: str, value: Any) -> Any:
    if key.lower() in REDACT_KEYS:
        return "[redacted]"
    if isinstance(value, dict):
        return {str(inner): _redact_value(str(inner), inner_value) for inner, inner_value in value.items()}
    return value


def redact_event_dict(
    _logger: object, _method: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    return {key: _redact_value(key, value) for key, value in event_dict.items()}


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            redact_event_dict,
            structlog.processors.JSONRenderer(),
        ]
    )
