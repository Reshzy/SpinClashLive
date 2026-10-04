from color_rush.domain.enums import RoundState
from color_rush.domain.errors import IllegalTransitionError

ALLOWED: dict[RoundState, frozenset[RoundState]] = {
    RoundState.WAITING: frozenset({RoundState.OPEN}),
    RoundState.OPEN: frozenset({RoundState.DRAINING, RoundState.CANCELLED}),
    RoundState.DRAINING: frozenset({RoundState.LOCKED, RoundState.CANCELLED}),
    RoundState.LOCKED: frozenset({RoundState.SPINNING, RoundState.CANCELLED}),
    RoundState.SPINNING: frozenset({RoundState.RESULT}),
    RoundState.RESULT: frozenset({RoundState.SETTLING}),
    RoundState.SETTLING: frozenset({RoundState.SETTLED}),
    RoundState.SETTLED: frozenset({RoundState.COOLDOWN}),
    RoundState.COOLDOWN: frozenset({RoundState.OPEN, RoundState.WAITING}),
    RoundState.CANCELLED: frozenset({RoundState.WAITING}),
}


def can_transition(current: RoundState, target: RoundState) -> bool:
    return target in ALLOWED.get(current, frozenset())


def require_transition(current: RoundState, target: RoundState) -> None:
    if not can_transition(current, target):
        raise IllegalTransitionError(f"cannot transition {current} -> {target}")


def cancel_allowed(current: RoundState) -> bool:
    return current in {RoundState.OPEN, RoundState.DRAINING, RoundState.LOCKED}
