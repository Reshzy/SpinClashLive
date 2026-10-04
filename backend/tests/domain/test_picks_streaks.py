import pytest

from color_rush.domain.enums import Color, DecisionReason
from color_rush.domain.picks import apply_pick
from color_rush.domain.streaks import StreakState, apply_streak


@pytest.mark.domain
def test_initial_pick_and_same_color_repeat() -> None:
    first = apply_pick(None, Color.RED, 1, 5)
    assert first.accepted
    assert first.state is not None
    assert first.state.change_count == 0
    repeat = apply_pick(first.state, Color.RED, 2, 5)
    assert repeat.reason is DecisionReason.ACCEPTED_REPEAT
    assert repeat.state is not None
    assert repeat.state.change_count == 0


@pytest.mark.domain
def test_five_changes_then_sixth_rejected() -> None:
    colors = [Color.RED, Color.GREEN, Color.GOLD, Color.RED, Color.GREEN, Color.GOLD]
    state = None
    for sequence, color in enumerate(colors, start=1):
        decision = apply_pick(state, color, sequence, 5)
        assert decision.accepted
        state = decision.state
    assert state is not None
    assert state.change_count == 5
    blocked = apply_pick(state, Color.RED, 7, 5)
    assert not blocked.accepted
    assert blocked.reason is DecisionReason.REJECTED_CHANGE_LIMIT


@pytest.mark.domain
def test_old_sequence_rejected() -> None:
    first = apply_pick(None, Color.RED, 10, 5)
    assert first.state is not None
    stale = apply_pick(first.state, Color.GREEN, 10, 5)
    assert stale.reason is DecisionReason.REJECTED_OLD_SEQUENCE
    older = apply_pick(first.state, Color.GREEN, 9, 5)
    assert older.reason is DecisionReason.REJECTED_OLD_SEQUENCE


@pytest.mark.domain
def test_streak_rules() -> None:
    start = StreakState(0, 0)
    win = apply_streak(start, correct=True)
    assert win == StreakState(1, 1)
    win2 = apply_streak(win, correct=True)
    assert win2 == StreakState(2, 2)
    lose = apply_streak(win2, correct=False)
    assert lose == StreakState(0, 2)
    # skipped/cancelled rounds do not call apply_streak
    assert win2.current == 2
