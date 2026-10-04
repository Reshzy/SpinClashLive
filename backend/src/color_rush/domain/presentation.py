from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from color_rush.domain.enums import Color
from color_rush.domain.rules import RoundRules

STRIP_LENGTH = 40
# One even and one odd gold index keeps 19 red / 19 green / 2 gold (47.5 / 47.5 / 5).
GOLD_INDEXES = (9, 28)
LAYOUT_VERSION = 1


def layout_v1_tiles() -> tuple[Color, ...]:
    tiles: list[Color] = []
    gold = set(GOLD_INDEXES)
    for index in range(STRIP_LENGTH):
        if index in gold:
            tiles.append(Color.GOLD)
        elif index % 2 == 0:
            tiles.append(Color.RED)
        else:
            tiles.append(Color.GREEN)
    return tuple(tiles)


def strip_indexes_for(color: Color) -> tuple[int, ...]:
    return tuple(index for index, tile in enumerate(layout_v1_tiles()) if tile is color)


def pick_target_slot(color: Color, animation_id: UUID) -> int:
    matching = strip_indexes_for(color)
    return matching[animation_id.int % len(matching)]


def compatible_slot(color: Color, requested_slot: int) -> int:
    tiles = layout_v1_tiles()
    if 0 <= requested_slot < len(tiles) and tiles[requested_slot] is color:
        return requested_slot
    matching = strip_indexes_for(color)
    return matching[0]


def tile_color_at(slot: int) -> Color:
    tiles = layout_v1_tiles()
    return tiles[slot % STRIP_LENGTH]


@dataclass(frozen=True, slots=True)
class PresentationPlan:
    animation_id: UUID
    starts_at: datetime
    ends_at: datetime
    duration_s: int
    layout_version: int
    target_color: Color
    target_slot: int
    target_offset: int

    def to_snapshot(self) -> dict[str, Any]:
        return {
            "animation_id": str(self.animation_id),
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "duration_s": self.duration_s,
            "layout_version": self.layout_version,
            "target_color": self.target_color.value,
            "target_slot": self.target_slot,
            "target_offset": self.target_offset,
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> PresentationPlan:
        color = Color(snapshot["target_color"])
        slot = compatible_slot(color, int(snapshot["target_slot"]))
        return cls(
            animation_id=UUID(snapshot["animation_id"]),
            starts_at=datetime.fromisoformat(snapshot["starts_at"]),
            ends_at=datetime.fromisoformat(snapshot["ends_at"]),
            duration_s=int(snapshot["duration_s"]),
            layout_version=int(snapshot["layout_version"]),
            target_color=color,
            target_slot=slot,
            target_offset=int(snapshot["target_offset"]),
        )


def build_presentation_plan(
    *,
    result: Color,
    started_at: datetime,
    rules: RoundRules,
    layout_version: int = LAYOUT_VERSION,
) -> PresentationPlan:
    animation_id = uuid4()
    slot = pick_target_slot(result, animation_id)
    return PresentationPlan(
        animation_id=animation_id,
        starts_at=started_at,
        ends_at=started_at + timedelta(seconds=rules.animation_s),
        duration_s=rules.animation_s,
        layout_version=layout_version,
        target_color=result,
        target_slot=slot,
        target_offset=0,
    )
