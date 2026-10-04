from collections.abc import Callable

from color_rush.domain.enums import Color
from color_rush.domain.errors import InvalidRulesError
from color_rush.domain.rules import WEIGHT_TOTAL, RoundRules

RngDraw = Callable[[int], int]


def color_for_draw(draw: int, rules: RoundRules) -> Color:
    if draw < 0 or draw >= WEIGHT_TOTAL:
        raise InvalidRulesError(f"draw must be in [0, {WEIGHT_TOTAL})")
    red_end = rules.red_weight
    green_end = red_end + rules.green_weight
    if draw < red_end:
        return Color.RED
    if draw < green_end:
        return Color.GREEN
    return Color.GOLD


def select_result(rng: RngDraw, rules: RoundRules) -> tuple[Color, int]:
    draw = rng(WEIGHT_TOTAL)
    return color_for_draw(draw, rules), draw
