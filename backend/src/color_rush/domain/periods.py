from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from color_rush.domain.enums import PeriodType
from color_rush.domain.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class PeriodWindow:
    period_type: PeriodType
    starts_at: datetime
    ends_at: datetime | None
    local_identity: str
    season_id: str | None = None


def ensure_aware(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        raise ConfigurationError("timestamps must be timezone-aware")
    return instant


def daily_window(instant: datetime, tz: ZoneInfo) -> PeriodWindow:
    instant = ensure_aware(instant)
    local = instant.astimezone(tz)
    start_local = datetime.combine(local.date(), time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return PeriodWindow(
        period_type=PeriodType.DAILY,
        starts_at=start_local.astimezone(UTC),
        ends_at=end_local.astimezone(UTC),
        local_identity=start_local.date().isoformat(),
    )


def weekly_window(instant: datetime, tz: ZoneInfo) -> PeriodWindow:
    instant = ensure_aware(instant)
    local = instant.astimezone(tz)
    monday = local.date() - timedelta(days=local.weekday())
    start_local = datetime.combine(monday, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=7)
    return PeriodWindow(
        period_type=PeriodType.WEEKLY,
        starts_at=start_local.astimezone(UTC),
        ends_at=end_local.astimezone(UTC),
        local_identity=start_local.date().isoformat(),
    )


def month_window(instant: datetime, tz: ZoneInfo) -> PeriodWindow:
    instant = ensure_aware(instant)
    local = instant.astimezone(tz)
    start_local = datetime(local.year, local.month, 1, tzinfo=tz)
    if local.month == 12:
        end_local = datetime(local.year + 1, 1, 1, tzinfo=tz)
    else:
        end_local = datetime(local.year, local.month + 1, 1, tzinfo=tz)
    return PeriodWindow(
        period_type=PeriodType.SEASON,
        starts_at=start_local.astimezone(UTC),
        ends_at=end_local.astimezone(UTC),
        local_identity=f"{start_local.year:04d}-{start_local.month:02d}",
    )


def all_time_window() -> PeriodWindow:
    return PeriodWindow(
        period_type=PeriodType.ALL_TIME,
        starts_at=datetime(1970, 1, 1, tzinfo=UTC),
        ends_at=None,
        local_identity="all-time",
    )


def contains(window: PeriodWindow, instant: datetime) -> bool:
    instant = ensure_aware(instant).astimezone(UTC)
    if instant < window.starts_at:
        return False
    if window.ends_at is None:
        return True
    return instant < window.ends_at


def windows_for(instant: datetime, tz: ZoneInfo, season: PeriodWindow | None) -> list[PeriodWindow]:
    daily = daily_window(instant, tz)
    weekly = weekly_window(instant, tz)
    season_window = season if season is not None and contains(season, instant) else month_window(instant, tz)
    return [daily, weekly, season_window, all_time_window()]
