from dataclasses import dataclass

from color_rush.domain.enums import Color
from color_rush.domain.rules import RoundRules


@dataclass(frozen=True, slots=True)
class ScoreOutcome:
    correct: bool
    points_delta: int


def score_pick(choice: Color, result: Color, rules: RoundRules) -> ScoreOutcome:
    correct = choice is result
    points = rules.effective_reward(choice) if correct else 0
    return ScoreOutcome(correct=correct, points_delta=points)
