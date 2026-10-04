from datetime import datetime
from typing import Protocol
from uuid import UUID


class Clock(Protocol):
    def now(self) -> datetime: ...


class Rng(Protocol):
    def below(self, upper: int) -> int: ...


class SystemClock:
    def now(self) -> datetime:
        from color_rush.domain.clock import utc_now

        return utc_now()


class SecureRng:
    def below(self, upper: int) -> int:
        from color_rush.domain.secure_rng import secrets_randbelow

        return secrets_randbelow(upper)


class FrozenClock:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def now(self) -> datetime:
        return self.instant

    def set(self, instant: datetime) -> None:
        self.instant = instant


class SequenceRng:
    def __init__(self, draws: list[int]) -> None:
        self._draws = list(draws)

    def below(self, upper: int) -> int:
        if not self._draws:
            raise RuntimeError("deterministic RNG exhausted")
        value = self._draws.pop(0)
        if value < 0 or value >= upper:
            raise RuntimeError(f"deterministic draw {value} outside [0, {upper})")
        return value


class SessionLockKey:
    @staticmethod
    def for_session(session_id: UUID) -> int:
        return int.from_bytes(session_id.bytes[:8], "big", signed=True)
