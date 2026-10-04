from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from color_rush.domain.enums import BonusType, Color
from color_rush.domain.errors import InvalidRulesError

WEIGHT_TOTAL = 1000
DEFAULT_TIMEZONE = "Asia/Manila"


@dataclass(frozen=True, slots=True)
class RoundRules:
    prediction_window_s: int = 30
    drain_bound_s: int = 5
    animation_s: int = 6
    result_display_s: int = 5
    cooldown_s: int = 3
    red_weight: int = 475
    green_weight: int = 475
    gold_weight: int = 50
    red_reward: int = 2
    green_reward: int = 2
    gold_reward: int = 14
    max_color_changes: int = 5
    bonus: BonusType = BonusType.NONE
    gold_bonus_reward: int = 28
    timezone: str = DEFAULT_TIMEZONE
    version: int = 1

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name, value in (
            ("prediction_window_s", self.prediction_window_s),
            ("drain_bound_s", self.drain_bound_s),
            ("animation_s", self.animation_s),
            ("result_display_s", self.result_display_s),
            ("cooldown_s", self.cooldown_s),
        ):
            if value <= 0:
                raise InvalidRulesError(f"{name} must be positive")
        if self.red_weight + self.green_weight + self.gold_weight != WEIGHT_TOTAL:
            raise InvalidRulesError("weights must total 1000")
        if min(self.red_weight, self.green_weight, self.gold_weight) < 0:
            raise InvalidRulesError("weights must be non-negative")
        for name, value in (
            ("red_reward", self.red_reward),
            ("green_reward", self.green_reward),
            ("gold_reward", self.gold_reward),
            ("gold_bonus_reward", self.gold_bonus_reward),
        ):
            if value < 0:
                raise InvalidRulesError(f"{name} cannot be negative")
        if self.max_color_changes < 0:
            raise InvalidRulesError("max_color_changes cannot be negative")
        if self.bonus not in BonusType:
            raise InvalidRulesError("unknown bonus")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise InvalidRulesError(f"unknown timezone {self.timezone}") from exc
        if self.version < 1:
            raise InvalidRulesError("version must be >= 1")

    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def base_reward(self, color: Color) -> int:
        if self.bonus is BonusType.GOLD_BONUS and color is Color.GOLD:
            return self.gold_bonus_reward
        return {
            Color.RED: self.red_reward,
            Color.GREEN: self.green_reward,
            Color.GOLD: self.gold_reward,
        }[color]

    def effective_reward(self, color: Color) -> int:
        reward = self.base_reward(color)
        if self.bonus is BonusType.DOUBLE_POINTS:
            return reward * 2
        return reward

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "prediction_window_s": self.prediction_window_s,
            "drain_bound_s": self.drain_bound_s,
            "animation_s": self.animation_s,
            "result_display_s": self.result_display_s,
            "cooldown_s": self.cooldown_s,
            "red_weight": self.red_weight,
            "green_weight": self.green_weight,
            "gold_weight": self.gold_weight,
            "red_reward": self.red_reward,
            "green_reward": self.green_reward,
            "gold_reward": self.gold_reward,
            "max_color_changes": self.max_color_changes,
            "bonus": self.bonus.value,
            "gold_bonus_reward": self.gold_bonus_reward,
            "timezone": self.timezone,
            "version": self.version,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> RoundRules:
        data = dict(snapshot)
        data["bonus"] = BonusType(data["bonus"])
        return cls(**data)
