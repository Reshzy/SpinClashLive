from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.application.players import player_ranks
from color_rush.application.source_health import session_source_health
from color_rush.domain.enums import Color, PeriodType
from color_rush.infrastructure.persistence.models import (
    ChampionAward,
    GameSession,
    LeaderboardPeriod,
    Pick,
    Player,
    Round,
)
from color_rush.infrastructure.redis.projections import (
    list_lookup,
    load_snapshot,
    project_round_counts,
    recent_history,
    redis_available,
    sanitize_name,
    store_snapshot,
    top_n,
)
from color_rush.infrastructure.security import new_token

HELP_CARD = {
    "title": "Color Rush Live",
    "commands": "!red / !gold / !green",
    "copy": (
        "Make your pick. Predictions open until picks locked. "
        "Points earned never go negative. Tie order is points then player id."
    ),
    "note": "Delivery is not guaranteed before the deadline.",
}


def build_snapshot(
    session: Session,
    redis: Any,
    game_session: GameSession,
    now: datetime,
) -> dict[str, Any]:
    rnd = session.get(Round, game_session.active_round_id) if game_session.active_round_id else None
    rules = rnd.rules_snapshot if rnd is not None else {}
    counts = {"red": 0, "gold": 0, "green": 0}
    recent_players: dict[str, list[dict[str, str]]] = {"red": [], "gold": [], "green": []}
    if rnd is not None and redis_available(redis):
        counts = project_round_counts(redis, session, game_session.game_id, rnd.id)
        for color in Color:
            names = redis.lrange(f"game:{game_session.game_id}:round:{rnd.id}:recent:{color.value}", 0, 9)
            recent_players[color.value] = [_split_recent(item) for item in names]
    elif rnd is not None:
        picks = list(session.scalars(select(Pick).where(Pick.round_id == rnd.id)))
        for pick in picks:
            counts[pick.choice] = counts.get(pick.choice, 0) + 1
            if len(recent_players[pick.choice]) < 10:
                player = session.get(Player, pick.player_id)
                recent_players[pick.choice].append(
                    {
                        "player_id": str(pick.player_id),
                        "name": sanitize_name(player.display_name if player else "player"),
                    }
                )

    leaderboard: dict[str, Any] = {"scope": "weekly", "period_id": None, "entries": []}
    weekly = session.scalar(
        select(LeaderboardPeriod)
        .where(
            LeaderboardPeriod.game_id == game_session.game_id,
            LeaderboardPeriod.period_type == PeriodType.WEEKLY.value,
        )
        .order_by(LeaderboardPeriod.starts_at.desc())
    )
    if weekly is not None:
        leaderboard["period_id"] = str(weekly.id)
        if redis_available(redis):
            entries = []
            for player_id, points, rank in top_n(redis, game_id=game_session.game_id, period_id=weekly.id, limit=10):
                player = session.get(Player, player_id)
                entries.append(
                    {
                        "rank": rank,
                        "player_id": str(player_id),
                        "display_name": sanitize_name(player.display_name if player else "player"),
                        "points": points,
                    }
                )
            leaderboard["entries"] = entries
        else:
            leaderboard["status"] = "Refreshing"

    history = recent_history(redis, game_session.game_id) if redis_available(redis) else []
    lookup = list_lookup(redis, game_session.game_id) if redis_available(redis) else []
    ceremony = None
    award = session.scalar(select(ChampionAward).order_by(ChampionAward.created_at.desc()))
    if award is not None:
        player = session.get(Player, award.player_id)
        ceremony = {
            "id": str(award.id),
            "title": award.display_title,
            "player_id": str(award.player_id),
            "display_name": sanitize_name(player.display_name if player else "player"),
        }

    health = session_source_health(session, game_session)
    data = {
        "state": rnd.state if rnd is not None else "waiting",
        "closes_at": rnd.scheduled_closes_at.isoformat() if rnd is not None and rnd.scheduled_closes_at else None,
        "rules": {
            "rewards": {
                "red": rules.get("red_reward", 2),
                "gold": rules.get("gold_reward", 14),
                "green": rules.get("green_reward", 2),
            },
            "bonus": rules.get("bonus", "none"),
        },
        "counts": counts,
        "recent_players": recent_players,
        "leaderboard": leaderboard,
        "recent_results": history,
        "source_status": health.value,
        "animation_plan": rnd.presentation_plan if rnd is not None else None,
        "lookup": lookup[:20],
        "ceremony": ceremony,
        "paused": game_session.paused,
        "mode": game_session.mode,
        "source_mode": game_session.source_mode,
        "game_id": str(game_session.game_id),
        "next_bonus": game_session.next_round_bonus,
        "next_gold_bonus_reward": game_session.next_round_gold_bonus_reward,
        "round_number": rnd.number if rnd is not None else None,
        "session_revision": game_session.revision,
        "help": HELP_CARD,
    }
    envelope = {
        "schema_version": 1,
        "type": "snapshot",
        "session_id": str(game_session.id),
        "round_id": str(rnd.id) if rnd is not None else None,
        "snapshot_sequence": 0,
        "server_time": now.isoformat(),
        "data": data,
    }
    if redis_available(redis):
        seq = store_snapshot(redis, game_session.game_id, envelope)
        envelope["snapshot_sequence"] = seq
    return envelope


def cached_or_build(session: Session, redis: Any, game_session: GameSession, now: datetime) -> dict[str, Any]:
    if redis_available(redis):
        cached = load_snapshot(redis, game_session.game_id)
        if cached is not None:
            return cached
    return build_snapshot(session, redis, game_session, now)


def enqueue_lookup_card(session: Session, redis: Any, game_id: UUID, player_id: UUID, now: datetime) -> None:
    from color_rush.infrastructure.redis.projections import push_lookup

    if not redis_available(redis):
        return
    payload = player_ranks(session, player_id, game_id)
    payload["expires_at"] = now.timestamp() + 60
    payload["request_id"] = new_token(8)
    push_lookup(redis, game_id, payload)


def _split_recent(item: str) -> dict[str, str]:
    player_id, _, name = item.partition(":")
    return {"player_id": player_id, "name": sanitize_name(name or "player")}
