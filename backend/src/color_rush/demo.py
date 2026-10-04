from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from color_rush.application.coordinator import Coordinator
from color_rush.application.dto import NormalizedCommand
from color_rush.application.ingest import append_and_process
from color_rush.application.periods import finalize_due_periods
from color_rush.application.ports import FrozenClock, SequenceRng
from color_rush.application.settlement import settle_round
from color_rush.composition import build_container
from color_rush.config import Settings
from color_rush.domain.commands import parse_command
from color_rush.domain.enums import SessionMode
from color_rush.domain.ranking import RankKey, ordinal_ranks
from color_rush.domain.rules import RoundRules
from color_rush.infrastructure.persistence.db import session_scope
from color_rush.infrastructure.persistence.models import LeaderboardPeriod, LeaderboardScore, Player


def _command(channel: str, name: str, text: str, published: datetime, message_id: str) -> NormalizedCommand:
    return NormalizedCommand(
        provider="simulation",
        provider_message_id=message_id,
        broadcast_id="demo-broadcast",
        provider_channel_id=channel,
        display_name=name,
        command_text=text,
        command=parse_command(text),
        published_at=published,
    )


def main() -> None:
    settings = Settings(color_rush_env="simulation")
    started = datetime(2026, 10, 4, 8, 0, tzinfo=UTC)
    clock = FrozenClock(started)
    rng = SequenceRng([960])
    container = build_container(settings, clock=clock, rng=rng)

    with session_scope(container.session_factory) as session:
        coordinator = Coordinator(
            session,
            clock=clock,
            rng=rng,
            owner_id="demo-worker",
            partition_count=4,
        )
        game = coordinator.create_game()
        game_session = coordinator.create_session(game.id, mode=SessionMode.MANUAL)
        token = coordinator.claim_lease(game_session.id).fencing_token
        rnd = coordinator.start_round(game_session.id, token, RoundRules())
        opened = rnd.opened_at
        assert opened is not None
        print(f"Predictions open  round={rnd.number} id={rnd.id}")

        commands = [
            _command("yt-alice", "Alice", "!red", opened + timedelta(seconds=1), "m1"),
            _command("yt-bob", "Bob", "!green", opened + timedelta(seconds=2), "m2"),
            _command("yt-cara", "Cara", "!gold", opened + timedelta(seconds=3), "m3"),
            _command("yt-drew", "Drew", "!red", opened + timedelta(seconds=4), "m4"),
            _command("yt-cara", "Cara", "!red", opened + timedelta(seconds=6), "m5"),
            _command("yt-cara", "Cara", "!gold", opened + timedelta(seconds=7), "m6"),
        ]
        ingested = append_and_process(session, session_id=game_session.id, commands=commands, checkpoint=None)
        print("ingest", [item.value for item in ingested.decisions])

        clock.set(opened + timedelta(seconds=10))
        rnd = coordinator.close_ingress(game_session.id, token, early=True)
        rnd = coordinator.complete_drain(game_session.id, token)
        print(f"Picks locked  cutoff={rnd.cutoff_sequence}")
        rnd = coordinator.spin(game_session.id, token)
        print(f"result={rnd.result}")
        coordinator.advance_after_spin(game_session.id, token)
        coordinator.advance_after_spin(game_session.id, token)
        settle_round(session, rnd.id, clock.now())
        rnd = coordinator.mark_settled(game_session.id, token)
        finalize_due_periods(session, game.id, clock.now())
        print(f"settled state={rnd.state}")

        names = {row.id: row.display_name for row in session.scalars(select(Player))}
        periods = session.scalars(select(LeaderboardPeriod).where(LeaderboardPeriod.game_id == game.id)).all()
        print("Four-scope scores")
        for period in periods:
            scores = list(
                session.scalars(select(LeaderboardScore).where(LeaderboardScore.period_id == period.id))
            )
            ranked = ordinal_ranks([RankKey(row.points, row.player_id) for row in scores])
            print(f"  {period.period_type} {period.local_identity}")
            for rank, key in ranked:
                print(f"    #{rank} {names.get(key.player_id, key.player_id)} {key.points}")


if __name__ == "__main__":
    main()
