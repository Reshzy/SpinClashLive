from __future__ import annotations

import time
from uuid import UUID

from sqlalchemy import select

from color_rush.application.settlement import all_partitions_complete, settle_round
from color_rush.composition import AppContainer, build_container
from color_rush.domain.enums import RoundState, SessionMode
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.db import session_scope
from color_rush.infrastructure.persistence.models import GameSession, Round
from color_rush.observability import configure_logging


def _tick_session(container: AppContainer, session_id: UUID) -> None:
    with session_scope(container.session_factory) as session:
        coordinator = container.coordinator(session)
        game_session = session.get(GameSession, session_id)
        if game_session is None:
            return
        token = coordinator.claim_lease(session_id).fencing_token
        rnd = session.get(Round, game_session.active_round_id) if game_session.active_round_id else None
        if rnd is None:
            if game_session.mode == SessionMode.AUTOMATIC.value and not game_session.paused:
                coordinator.start_round(session_id, token, RoundRules())
            return
        state = RoundState(rnd.state)
        if state is RoundState.OPEN:
            coordinator.maybe_close_due_rounds(session_id, token)
        elif state is RoundState.DRAINING:
            coordinator.complete_drain(session_id, token)
        elif state is RoundState.LOCKED and game_session.mode == SessionMode.AUTOMATIC.value:
            coordinator.spin(session_id, token)
        elif state in {RoundState.SPINNING, RoundState.RESULT}:
            coordinator.advance_after_spin(session_id, token)
        elif state is RoundState.SETTLING:
            settle_round(session, rnd.id, container.clock.now())
            if all_partitions_complete(session, rnd.id):
                coordinator.mark_settled(session_id, token)
        elif state is RoundState.SETTLED:
            coordinator.enter_cooldown(session_id, token)


def run_forever() -> None:
    configure_logging()
    container = build_container()
    settings = container.settings
    while True:
        with session_scope(container.session_factory) as session:
            session_ids = list(session.scalars(select(GameSession.id)))
        for session_id in session_ids:
            try:
                _tick_session(container, session_id)
            except Exception:
                continue
        time.sleep(max(settings.drain_poll_interval_ms / 1000.0, 0.05))


def main() -> None:
    run_forever()


if __name__ == "__main__":
    main()
