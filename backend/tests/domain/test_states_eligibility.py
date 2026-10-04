from datetime import UTC, datetime, timedelta

import pytest

from color_rush.domain.eligibility import classify_pick_eligibility
from color_rush.domain.enums import DecisionReason, RoundState
from color_rush.domain.errors import IllegalTransitionError
from color_rush.domain.states import can_transition, require_transition


@pytest.mark.domain
def test_state_machine() -> None:
    assert can_transition(RoundState.WAITING, RoundState.OPEN)
    assert can_transition(RoundState.OPEN, RoundState.DRAINING)
    assert can_transition(RoundState.DRAINING, RoundState.LOCKED)
    assert can_transition(RoundState.LOCKED, RoundState.SPINNING)
    assert can_transition(RoundState.SPINNING, RoundState.RESULT)
    assert can_transition(RoundState.RESULT, RoundState.SETTLING)
    assert can_transition(RoundState.SETTLING, RoundState.SETTLED)
    assert can_transition(RoundState.SETTLED, RoundState.COOLDOWN)
    assert can_transition(RoundState.COOLDOWN, RoundState.OPEN)
    assert can_transition(RoundState.OPEN, RoundState.CANCELLED)
    assert not can_transition(RoundState.SPINNING, RoundState.CANCELLED)
    with pytest.raises(IllegalTransitionError):
        require_transition(RoundState.LOCKED, RoundState.OPEN)


@pytest.mark.domain
def test_eligibility_windows() -> None:
    opened = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)
    closes = opened + timedelta(seconds=30)
    ok = classify_pick_eligibility(
        round_state=RoundState.OPEN,
        opened_at=opened,
        scheduled_closes_at=closes,
        received_at=opened + timedelta(seconds=10),
        published_at=opened + timedelta(seconds=9),
    )
    assert ok is None
    late = classify_pick_eligibility(
        round_state=RoundState.OPEN,
        opened_at=opened,
        scheduled_closes_at=closes,
        received_at=closes,
        published_at=opened + timedelta(seconds=1),
    )
    assert late is DecisionReason.REJECTED_LATE_RECEIPT
    history = classify_pick_eligibility(
        round_state=RoundState.OPEN,
        opened_at=opened,
        scheduled_closes_at=closes,
        received_at=opened + timedelta(seconds=1),
        published_at=opened - timedelta(seconds=1),
    )
    assert history is DecisionReason.REJECTED_HISTORICAL
    after_cutoff = classify_pick_eligibility(
        round_state=RoundState.DRAINING,
        opened_at=opened,
        scheduled_closes_at=closes,
        received_at=closes + timedelta(seconds=1),
        published_at=opened + timedelta(seconds=1),
        cutoff_sequence=10,
        sequence=11,
    )
    assert after_cutoff is DecisionReason.REJECTED_AFTER_CUTOFF
