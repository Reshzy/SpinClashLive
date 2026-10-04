import pytest

from color_rush.domain.enums import BonusType, Color
from color_rush.domain.errors import InvalidRulesError
from color_rush.domain.rng import color_for_draw, select_result
from color_rush.domain.rules import RoundRules
from color_rush.domain.scoring import score_pick


@pytest.mark.domain
def test_weight_boundaries() -> None:
    rules = RoundRules()
    assert color_for_draw(0, rules) is Color.RED
    assert color_for_draw(474, rules) is Color.RED
    assert color_for_draw(475, rules) is Color.GREEN
    assert color_for_draw(949, rules) is Color.GREEN
    assert color_for_draw(950, rules) is Color.GOLD
    assert color_for_draw(999, rules) is Color.GOLD


@pytest.mark.domain
def test_draw_out_of_range() -> None:
    with pytest.raises(InvalidRulesError):
        color_for_draw(-1, RoundRules())
    with pytest.raises(InvalidRulesError):
        color_for_draw(1000, RoundRules())


@pytest.mark.domain
def test_injected_rng() -> None:
    color, draw = select_result(lambda _upper: 950, RoundRules())
    assert color is Color.GOLD
    assert draw == 950


@pytest.mark.domain
@pytest.mark.parametrize(
    ("choice", "result", "points"),
    [
        (Color.RED, Color.RED, 2),
        (Color.GREEN, Color.GREEN, 2),
        (Color.GOLD, Color.GOLD, 14),
        (Color.RED, Color.GREEN, 0),
        (Color.GOLD, Color.RED, 0),
    ],
)
def test_base_rewards(choice: Color, result: Color, points: int) -> None:
    assert score_pick(choice, result, RoundRules()).points_delta == points


@pytest.mark.domain
def test_double_points_bonus() -> None:
    rules = RoundRules(bonus=BonusType.DOUBLE_POINTS)
    assert score_pick(Color.RED, Color.RED, rules).points_delta == 4
    assert score_pick(Color.GOLD, Color.GOLD, rules).points_delta == 28
    assert score_pick(Color.GREEN, Color.RED, rules).points_delta == 0


@pytest.mark.domain
def test_gold_bonus() -> None:
    rules = RoundRules(bonus=BonusType.GOLD_BONUS, gold_bonus_reward=28)
    assert score_pick(Color.GOLD, Color.GOLD, rules).points_delta == 28
    assert score_pick(Color.RED, Color.RED, rules).points_delta == 2


@pytest.mark.domain
def test_invalid_weights() -> None:
    with pytest.raises(InvalidRulesError):
        RoundRules(red_weight=500, green_weight=500, gold_weight=1)
