"""Low-cardinality Prometheus metrics. Labels are finite enums, never player or message IDs."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

INGEST_DECISIONS = Counter(
    "color_rush_ingest_decisions_total",
    "Ingest command decisions by bounded reason class",
    ["class_"],
)
INGEST_DUPLICATES = Counter(
    "color_rush_ingest_duplicates_total",
    "Duplicate provider message IDs skipped before insert",
)
HTTP_REQUESTS = Counter(
    "color_rush_http_requests_total",
    "HTTP requests by route template, method, and status class",
    ["route", "method", "status_class"],
)
SOURCE_LAG_MS = Gauge("color_rush_source_lag_ms", "Latest source lag in milliseconds")
INBOX_BACKLOG = Gauge("color_rush_inbox_backlog", "Pending inbox row count")
INBOX_OLDEST_AGE_S = Gauge("color_rush_inbox_oldest_age_seconds", "Age of oldest pending inbox row")
SETTLEMENT_LAG_S = Gauge("color_rush_settlement_lag_seconds", "Seconds a settling round has waited")
PROJECTION_PENDING = Gauge("color_rush_projection_pending", "Pending projection jobs")
OUTBOX_PENDING = Gauge("color_rush_outbox_pending", "Unpublished outbox rows")
SNAPSHOT_BYTES = Histogram(
    "color_rush_snapshot_bytes",
    "Serialized snapshot payload bytes",
    buckets=(2048, 8192, 16384, 32768, 65536),
)
SNAPSHOT_DROPPED = Counter("color_rush_snapshot_dropped_total", "Snapshots dropped for slow WebSocket clients")
SNAPSHOT_COALESCED = Counter(
    "color_rush_snapshot_coalesced_total",
    "Superseded snapshot updates coalesced before send",
)
REDIS_UP = Gauge("color_rush_redis_up", "1 if Redis ping succeeds")
POSTGRES_UP = Gauge("color_rush_postgres_up", "1 if PostgreSQL ping succeeds")
SOURCE_HEALTH = Gauge(
    "color_rush_source_health",
    "Source health ordinal (0 healthy)",
    ["status"],
)

_DECISION_CLASS = {
    "accepted_new": "accepted",
    "accepted_change": "accepted",
    "accepted_repeat": "accepted",
    "rejected_late_receipt": "late",
    "rejected_historical": "late",
    "rejected_after_cutoff": "late",
    "throttled_lookup": "throttled",
    "help_cooldown": "throttled",
    "ignored_lookup": "ignored",
    "ignored_help": "ignored",
    "ignored_invalid": "ignored",
    "rejected_old_sequence": "rejected",
    "rejected_change_limit": "rejected",
    "rejected_not_open": "rejected",
    "rejected_blocked": "rejected",
    "rejected_unknown_command": "rejected",
}


def record_decision(reason: str) -> None:
    INGEST_DECISIONS.labels(class_=_DECISION_CLASS.get(reason, "rejected")).inc()


def record_duplicate() -> None:
    INGEST_DUPLICATES.inc()


def record_http(route: str, method: str, status_code: int) -> None:
    HTTP_REQUESTS.labels(route=route, method=method, status_class=f"{status_code // 100}xx").inc()


def record_snapshot_bytes(size: int) -> None:
    SNAPSHOT_BYTES.observe(size)
