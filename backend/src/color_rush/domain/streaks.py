from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StreakState:
    current: int
    best: int


def apply_streak(state: StreakState, *, correct: bool) -> StreakState:
    current = state.current + 1 if correct else 0
    best = max(state.best, current)
    return StreakState(current=current, best=best)
