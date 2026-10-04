from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest

from color_rush.domain.periods import all_time_window, contains, daily_window, month_window, weekly_window
from color_rush.domain.ranking import RankKey, ordinal_ranks

MANILA = ZoneInfo("Asia/Manila")


@pytest.mark.domain
def test_midnight_belongs_to_new_day() -> None:
    midnight = datetime(2026, 10, 5, 0, 0, tzinfo=MANILA)
    window = daily_window(midnight, MANILA)
    assert contains(window, midnight)
    prior = datetime(2026, 10, 4, 23, 59, 59, tzinfo=MANILA)
    prior_window = daily_window(prior, MANILA)
    assert prior_window.local_identity == "2026-10-04"
    assert window.local_identity == "2026-10-05"
    assert not contains(prior_window, midnight)


@pytest.mark.domain
def test_monday_week_identity() -> None:
    sunday = datetime(2026, 10, 4, 12, 0, tzinfo=MANILA)  # Sunday
    monday = datetime(2026, 10, 5, 0, 0, tzinfo=MANILA)
    assert weekly_window(sunday, MANILA).local_identity == "2026-09-28"
    assert weekly_window(monday, MANILA).local_identity == "2026-10-05"


@pytest.mark.domain
def test_tie_order_points_then_uuid() -> None:
    low = UUID("00000000-0000-0000-0000-000000000001")
    high = UUID("00000000-0000-0000-0000-0000000000ff")
    ranked = ordinal_ranks([RankKey(10, high), RankKey(10, low), RankKey(0, high)])
    assert [item.player_id for _, item in ranked] == [low, high, high]
    assert [rank for rank, _ in ranked] == [1, 2, 3]
    assert ranked[2][1].points == 0


@pytest.mark.domain
def test_season_month_boundary_and_all_time() -> None:
    october = datetime(2026, 10, 31, 23, 59, 59, tzinfo=MANILA)
    november = datetime(2026, 11, 1, 0, 0, tzinfo=MANILA)
    oct_window = month_window(october, MANILA)
    nov_window = month_window(november, MANILA)
    assert oct_window.local_identity == "2026-10"
    assert nov_window.local_identity == "2026-11"
    assert contains(oct_window, october)
    assert not contains(oct_window, november)
    forever = all_time_window()
    assert contains(forever, october)
    assert contains(forever, november)
