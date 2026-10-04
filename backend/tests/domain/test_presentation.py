from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from color_rush.domain.enums import Color
from color_rush.domain.presentation import (
    GOLD_INDEXES,
    LAYOUT_VERSION,
    STRIP_LENGTH,
    build_presentation_plan,
    compatible_slot,
    layout_v1_tiles,
    pick_target_slot,
    strip_indexes_for,
    tile_color_at,
)
from color_rush.domain.rules import RoundRules


@pytest.mark.domain
def test_layout_weights_match_47_5_47_5_5() -> None:
    tiles = layout_v1_tiles()
    assert len(tiles) == STRIP_LENGTH
    assert tiles.count(Color.RED) == 19
    assert tiles.count(Color.GREEN) == 19
    assert tiles.count(Color.GOLD) == 2
    assert GOLD_INDEXES == (9, 28)
    assert tiles[9] is Color.GOLD
    assert tiles[28] is Color.GOLD


@pytest.mark.domain
@pytest.mark.parametrize("color", list(Color))
def test_pick_target_slot_matches_color(color: Color) -> None:
    for _ in range(20):
        slot = pick_target_slot(color, uuid4())
        assert tile_color_at(slot) is color
        assert slot in strip_indexes_for(color)


@pytest.mark.domain
def test_pick_target_slot_is_deterministic() -> None:
    animation_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert pick_target_slot(Color.GOLD, animation_id) == pick_target_slot(Color.GOLD, animation_id)


@pytest.mark.domain
def test_compatible_slot_keeps_matching_and_repairs_mismatch() -> None:
    gold_slot = strip_indexes_for(Color.GOLD)[0]
    assert compatible_slot(Color.GOLD, gold_slot) == gold_slot
    repaired = compatible_slot(Color.GOLD, 0)
    assert tile_color_at(repaired) is Color.GOLD


@pytest.mark.domain
def test_build_presentation_plan_persists_matching_slot() -> None:
    started = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)
    for color in Color:
        plan = build_presentation_plan(result=color, started_at=started, rules=RoundRules(animation_s=6))
        assert plan.layout_version == LAYOUT_VERSION
        assert plan.target_color is color
        assert tile_color_at(plan.target_slot) is color
        assert plan.duration_s == 6
        restored = plan.from_snapshot(plan.to_snapshot())
        assert restored.target_slot == plan.target_slot
        assert restored.target_color is color
