from datetime import datetime

from color_rush.domain.enums import DecisionReason, RoundState


def classify_pick_eligibility(
    *,
    round_state: RoundState | None,
    opened_at: datetime | None,
    scheduled_closes_at: datetime | None,
    received_at: datetime,
    published_at: datetime,
    cutoff_sequence: int | None = None,
    sequence: int | None = None,
) -> DecisionReason | None:
    """Return a rejection reason, or None if the command may be applied."""
    if round_state is None or opened_at is None or scheduled_closes_at is None:
        return DecisionReason.REJECTED_NOT_OPEN
    if published_at < opened_at:
        return DecisionReason.REJECTED_HISTORICAL
    if cutoff_sequence is not None and sequence is not None and sequence > cutoff_sequence:
        return DecisionReason.REJECTED_AFTER_CUTOFF
    if round_state is RoundState.OPEN:
        if received_at < opened_at or received_at >= scheduled_closes_at:
            return DecisionReason.REJECTED_LATE_RECEIPT
        return None
    if round_state is RoundState.DRAINING:
        if cutoff_sequence is None or sequence is None or sequence > cutoff_sequence:
            return DecisionReason.REJECTED_AFTER_CUTOFF
        if published_at < opened_at:
            return DecisionReason.REJECTED_HISTORICAL
        return None
    return DecisionReason.REJECTED_NOT_OPEN
