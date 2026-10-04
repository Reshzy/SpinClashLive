from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from color_rush.domain.enums import Color
from color_rush.domain.rules import RoundRules


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
        return cls(
            animation_id=UUID(snapshot["animation_id"]),
            starts_at=datetime.fromisoformat(snapshot["starts_at"]),
            ends_at=datetime.fromisoformat(snapshot["ends_at"]),
            duration_s=int(snapshot["duration_s"]),
            layout_version=int(snapshot["layout_version"]),
            target_color=Color(snapshot["target_color"]),
            target_slot=int(snapshot["target_slot"]),
            target_offset=int(snapshot["target_offset"]),
        )


def build_presentation_plan(
    *,
    result: Color,
    started_at: datetime,
    rules: RoundRules,
    layout_version: int = 1,
) -> PresentationPlan:
    slot = {Color.RED: 0, Color.GOLD: 1, Color.GREEN: 2}[result]
    return PresentationPlan(
        animation_id=uuid4(),
        starts_at=started_at,
        ends_at=started_at + timedelta(seconds=rules.animation_s),
        duration_s=rules.animation_s,
        layout_version=layout_version,
        target_color=result,
        target_slot=slot,
        target_offset=0,
    )
