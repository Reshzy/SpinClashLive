from datetime import UTC, datetime

from color_rush.application.snapshots import award_status_for, overlay_rules_view, rotating_scope
from color_rush.domain.enums import BonusType, PeriodType, RoundState
from color_rush.domain.rules import RoundRules


def test_rotating_scope_cycle() -> None:
    weekly = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)
    assert rotating_scope(weekly) is PeriodType.WEEKLY
    assert rotating_scope(datetime.fromtimestamp(weekly.timestamp() + 20, tz=UTC)) is PeriodType.DAILY
    assert rotating_scope(datetime.fromtimestamp(weekly.timestamp() + 40, tz=UTC)) is PeriodType.SEASON
    assert rotating_scope(datetime.fromtimestamp(weekly.timestamp() + 100, tz=UTC)) is PeriodType.ALL_TIME


def test_award_status_for_phases() -> None:
    assert award_status_for(RoundState.OPEN.value) == "none"
    assert award_status_for(RoundState.SPINNING.value) == "pending"
    assert award_status_for(RoundState.RESULT.value) == "pending"
    assert award_status_for(RoundState.SETTLING.value) == "pending"
    assert award_status_for(RoundState.SETTLED.value) == "committed"
    assert award_status_for(RoundState.CANCELLED.value) == "cancelled"
    assert award_status_for(None) == "none"


def test_overlay_rules_view_uses_effective_rewards() -> None:
    doubled = overlay_rules_view(RoundRules(bonus=BonusType.DOUBLE_POINTS).to_snapshot())
    assert doubled["rewards"]["red"] == 4
    assert doubled["rewards"]["gold"] == 28
    assert doubled["bonus"] == "double_points"
    assert doubled["weights"]["gold"] == 50
    gold = overlay_rules_view(RoundRules(bonus=BonusType.GOLD_BONUS, gold_bonus_reward=28).to_snapshot())
    assert gold["rewards"]["gold"] == 28
    assert gold["rewards"]["red"] == 2
    empty = overlay_rules_view(None)
    assert empty["rewards"]["red"] == 2
    assert empty["percentages"]["gold"] == 5.0
