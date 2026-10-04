from dataclasses import dataclass

from color_rush.domain.enums import Color, DecisionReason


@dataclass(frozen=True, slots=True)
class PickState:
    choice: Color
    last_sequence: int
    change_count: int


@dataclass(frozen=True, slots=True)
class PickDecision:
    accepted: bool
    reason: DecisionReason
    state: PickState | None


def apply_pick(
    current: PickState | None,
    choice: Color,
    sequence: int,
    max_color_changes: int,
) -> PickDecision:
    if current is None:
        return PickDecision(
            True,
            DecisionReason.ACCEPTED_NEW,
            PickState(choice=choice, last_sequence=sequence, change_count=0),
        )
    if sequence <= current.last_sequence:
        return PickDecision(False, DecisionReason.REJECTED_OLD_SEQUENCE, current)
    if choice is current.choice:
        return PickDecision(
            True,
            DecisionReason.ACCEPTED_REPEAT,
            PickState(
                choice=choice,
                last_sequence=sequence,
                change_count=current.change_count,
            ),
        )
    if current.change_count >= max_color_changes:
        return PickDecision(False, DecisionReason.REJECTED_CHANGE_LIMIT, current)
    return PickDecision(
        True,
        DecisionReason.ACCEPTED_CHANGE,
        PickState(
            choice=choice,
            last_sequence=sequence,
            change_count=current.change_count + 1,
        ),
    )
