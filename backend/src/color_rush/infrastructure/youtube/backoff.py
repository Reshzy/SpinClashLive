from __future__ import annotations

import random
import time
from collections.abc import Callable

from color_rush.domain.enums import SourceHealth

TERMINAL = frozenset(
    {
        SourceHealth.DISABLED,
        SourceHealth.ENDED,
        SourceHealth.PERMISSION,
        SourceHealth.RESYNC,
    }
)


def sleep_backoff(
    attempt: int, *, base: float = 0.5, cap: float = 30.0, rng: Callable[[], float] | None = None
) -> float:
    delay = min(cap, base * (2 ** max(attempt - 1, 0)))
    jitter = (rng or random.random)() * delay * 0.25
    wait = delay + jitter
    time.sleep(wait)
    return float(wait)


def should_stop(health: SourceHealth, attempt: int, budget: int = 8) -> bool:
    if health in TERMINAL:
        return True
    return attempt >= budget
