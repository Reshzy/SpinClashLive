from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.dto import IngestResult, NormalizedCommand, SourceCheckpointData
from color_rush.domain.commands import parse_command
from color_rush.domain.eligibility import classify_pick_eligibility
from color_rush.domain.enums import (
    COLOR_BY_COMMAND,
    PICK_COMMANDS,
    CommandType,
    DecisionReason,
    ProcessingStatus,
    RoundState,
)
from color_rush.domain.picks import PickState, apply_pick
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.db import acquire_session_lock, database_clock
from color_rush.infrastructure.persistence.models import (
    CommandInbox,
    GameSession,
    Pick,
    Player,
    PlayerModeration,
    Round,
    SourceCheckpoint,
)


def _get_or_create_player(
    session: Session, command: NormalizedCommand, received_at: datetime
) -> Player:
    player = session.scalar(
        select(Player).where(
            Player.provider == command.provider,
            Player.provider_channel_id == command.provider_channel_id,
        )
    )
    if player is None:
        player = Player(
            id=uuid4(),
            provider=command.provider,
            provider_channel_id=command.provider_channel_id,
            display_name=command.display_name[:128],
            avatar_ref=None,
            profile_refreshed_at=None,
            created_at=received_at,
            last_seen_at=received_at,
        )
        session.add(player)
        session.flush()
        return player
    player.display_name = command.display_name[:128]
    player.last_seen_at = received_at
    return player


def _is_blocked(session: Session, player_id: UUID, session_id: UUID, game_id: UUID) -> bool:
    scopes = (f"session:{session_id}", f"game:{game_id}")
    row = session.scalar(
        select(PlayerModeration).where(
            PlayerModeration.player_id == player_id,
            PlayerModeration.scope_key.in_(scopes),
            PlayerModeration.blocked.is_(True),
        )
    )
    return row is not None


def append_and_process(
    session: Session,
    *,
    session_id: UUID,
    commands: list[NormalizedCommand],
    checkpoint: SourceCheckpointData | None,
) -> IngestResult:
    """Append inbox rows under the session advisory lock, then apply eligible picks."""
    acquire_session_lock(session, session_id)
    received_at = database_clock(session)
    game_session = session.get(GameSession, session_id)
    if game_session is None:
        raise ValueError("unknown session")
    active_round = session.get(Round, game_session.active_round_id) if game_session.active_round_id else None

    sequences: list[int] = []
    decisions: list[DecisionReason] = []
    pending_rows: list[CommandInbox] = []

    for command in commands:
        duplicate = session.scalar(
            select(CommandInbox.id).where(
                CommandInbox.provider == command.provider,
                CommandInbox.broadcast_id == command.broadcast_id,
                CommandInbox.provider_message_id == command.provider_message_id,
            )
        )
        if duplicate is not None:
            continue
        parsed = command.command if command.command is not None else parse_command(command.command_text)
        seq = game_session.next_inbox_sequence
        game_session.next_inbox_sequence = seq + 1
        player = _get_or_create_player(session, command, received_at)
        reason: DecisionReason
        status: ProcessingStatus
        candidate: UUID | None = active_round.id if active_round is not None else None

        if parsed is None:
            reason = DecisionReason.IGNORED_INVALID
            status = ProcessingStatus.IGNORED
        elif parsed in {CommandType.SCORE, CommandType.RANK}:
            reason = DecisionReason.IGNORED_LOOKUP
            status = ProcessingStatus.IGNORED
        elif parsed is CommandType.HELP:
            reason = DecisionReason.IGNORED_HELP
            status = ProcessingStatus.IGNORED
        else:
            reason = DecisionReason.REJECTED_NOT_OPEN
            status = ProcessingStatus.REJECTED

        row = CommandInbox(
            id=uuid4(),
            session_id=session_id,
            sequence=seq,
            provider=command.provider,
            provider_message_id=command.provider_message_id,
            broadcast_id=command.broadcast_id,
            candidate_round_id=candidate,
            player_id=player.id,
            command=parsed.value if parsed else "invalid",
            published_at=command.published_at,
            received_at=received_at,
            processing_status=status.value,
            decision_reason=reason.value,
        )
        session.add(row)
        pending_rows.append(row)
        sequences.append(seq)

    session.flush()

    for row in pending_rows:
        parsed = None if row.command == "invalid" else CommandType(row.command)
        if parsed is None or parsed not in PICK_COMMANDS:
            decisions.append(DecisionReason(row.decision_reason))
            continue
        if _is_blocked(session, row.player_id, session_id, game_session.game_id):
            row.processing_status = ProcessingStatus.REJECTED.value
            row.decision_reason = DecisionReason.REJECTED_BLOCKED.value
            decisions.append(DecisionReason.REJECTED_BLOCKED)
            continue
        if active_round is None:
            row.processing_status = ProcessingStatus.REJECTED.value
            row.decision_reason = DecisionReason.REJECTED_NOT_OPEN.value
            decisions.append(DecisionReason.REJECTED_NOT_OPEN)
            continue
        reject = classify_pick_eligibility(
            round_state=RoundState(active_round.state),
            opened_at=active_round.opened_at,
            scheduled_closes_at=active_round.scheduled_closes_at,
            received_at=row.received_at,
            published_at=row.published_at,
            cutoff_sequence=active_round.cutoff_sequence,
            sequence=row.sequence,
        )
        if reject is not None:
            row.processing_status = ProcessingStatus.REJECTED.value
            row.decision_reason = reject.value
            decisions.append(reject)
            continue
        decision = _apply_inbox_pick(session, active_round, row, parsed)
        decisions.append(decision)

    if checkpoint is not None:
        existing = session.get(SourceCheckpoint, checkpoint.broadcast_id)
        if existing is None:
            session.add(
                SourceCheckpoint(
                    broadcast_id=checkpoint.broadcast_id,
                    next_page_token=checkpoint.next_page_token,
                    source_mode=checkpoint.source_mode,
                    last_success_at=received_at,
                    ownership_token=checkpoint.ownership_token,
                )
            )
        else:
            existing.next_page_token = checkpoint.next_page_token
            existing.source_mode = checkpoint.source_mode
            existing.last_success_at = received_at
            existing.ownership_token = checkpoint.ownership_token

    game_session.updated_at = received_at
    return IngestResult(tuple(sequences), tuple(decisions), received_at)


def _apply_inbox_pick(
    session: Session,
    active_round: Round,
    row: CommandInbox,
    command: CommandType,
) -> DecisionReason:
    rules = RoundRules.from_snapshot(active_round.rules_snapshot)
    existing = session.scalar(
        select(Pick).where(Pick.round_id == active_round.id, Pick.player_id == row.player_id)
    )
    current = None
    if existing is not None:
        from color_rush.domain.enums import Color

        current = PickState(
            choice=Color(existing.choice),
            last_sequence=existing.last_sequence,
            change_count=existing.change_count,
        )
    result = apply_pick(current, COLOR_BY_COMMAND[command], row.sequence, rules.max_color_changes)
    if not result.accepted or result.state is None:
        row.processing_status = ProcessingStatus.REJECTED.value
        row.decision_reason = result.reason.value
        return result.reason
    if existing is None:
        session.add(
            Pick(
                id=uuid4(),
                round_id=active_round.id,
                player_id=row.player_id,
                choice=result.state.choice.value,
                last_sequence=result.state.last_sequence,
                change_count=result.state.change_count,
                first_received_at=row.received_at,
                updated_at=row.received_at,
            )
        )
    else:
        existing.choice = result.state.choice.value
        existing.last_sequence = result.state.last_sequence
        existing.change_count = result.state.change_count
        existing.updated_at = row.received_at
    row.processing_status = ProcessingStatus.ACCEPTED.value
    row.decision_reason = result.reason.value
    row.candidate_round_id = active_round.id
    return result.reason


def process_eligible_inbox(session: Session, round_id: UUID) -> int:
    """Process PENDING/REJECTED-not-yet-applied eligible rows up to the frozen cutoff."""
    rnd = session.get(Round, round_id)
    if rnd is None or rnd.cutoff_sequence is None:
        return 0
    rows = session.scalars(
        select(CommandInbox)
        .where(
            CommandInbox.session_id == rnd.session_id,
            CommandInbox.sequence <= rnd.cutoff_sequence,
            CommandInbox.processing_status.in_(
                (ProcessingStatus.PENDING.value, ProcessingStatus.REJECTED.value)
            ),
        )
        .order_by(CommandInbox.sequence)
    ).all()
    processed = 0
    for row in rows:
        if row.command not in {item.value for item in PICK_COMMANDS}:
            continue
        if row.processing_status == ProcessingStatus.ACCEPTED.value:
            continue
        command = CommandType(row.command)
        reject = classify_pick_eligibility(
            round_state=RoundState.DRAINING,
            opened_at=rnd.opened_at,
            scheduled_closes_at=rnd.scheduled_closes_at,
            received_at=row.received_at,
            published_at=row.published_at,
            cutoff_sequence=rnd.cutoff_sequence,
            sequence=row.sequence,
        )
        if reject is not None:
            row.processing_status = ProcessingStatus.REJECTED.value
            row.decision_reason = reject.value
            processed += 1
            continue
        _apply_inbox_pick(session, rnd, row, command)
        processed += 1
    return processed
