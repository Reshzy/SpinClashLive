from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from color_rush.application.players import player_ranks
from color_rush.application.source_health import session_source_health
from color_rush.domain.enums import Color, PeriodStatus, PeriodType, RoundState
from color_rush.domain.rules import RoundRules
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
        "Points earned never go negative. Tie order is points then player id. "
        "Chances are 47.5% Red, 47.5% Green, 5% Gold."
    ),
    "note": "Delivery is not guaranteed before the deadline.",
    "percentages": {"red": 47.5, "gold": 5.0, "green": 47.5},
}

LEADERBOARD_ROTATION_S = 20
SCOPE_TITLES = {
    PeriodType.WEEKLY: "Weekly",
    PeriodType.DAILY: "Daily",
    PeriodType.SEASON: "Season",
    PeriodType.ALL_TIME: "All-Time",
}
_ROTATION_CYCLE = (
    PeriodType.WEEKLY,
    PeriodType.DAILY,
    PeriodType.SEASON,
    PeriodType.WEEKLY,
    PeriodType.DAILY,
    PeriodType.ALL_TIME,
)


def rotating_scope(now: datetime) -> PeriodType:
    index = int(now.timestamp() // LEADERBOARD_ROTATION_S) % len(_ROTATION_CYCLE)
    return _ROTATION_CYCLE[index]


def award_status_for(state: str | None) -> str:
    if state in {RoundState.SPINNING.value, RoundState.RESULT.value, RoundState.SETTLING.value}:
        return "pending"
    if state == RoundState.SETTLED.value:
        return "committed"
    if state == RoundState.CANCELLED.value:
        return "cancelled"
    return "none"


def overlay_rules_view(raw: dict[str, Any] | None) -> dict[str, Any]:
    try:
        rules = RoundRules.from_snapshot(raw or {})
    except Exception:
        rules = RoundRules()
    return {
        "rewards": {
            "red": rules.effective_reward(Color.RED),
            "gold": rules.effective_reward(Color.GOLD),
            "green": rules.effective_reward(Color.GREEN),
        },
        "weights": {
            "red": rules.red_weight,
            "gold": rules.gold_weight,
            "green": rules.green_weight,
        },
        "bonus": rules.bonus.value,
        "gold_bonus_reward": rules.gold_bonus_reward,
        "percentages": {"red": 47.5, "gold": 5.0, "green": 47.5},
    }


def build_snapshot(
    session: Session,
    redis: Any,
    game_session: GameSession,
    now: datetime,
) -> dict[str, Any]:
    rnd = session.get(Round, game_session.active_round_id) if game_session.active_round_id else None
    state = rnd.state if rnd is not None else RoundState.WAITING.value
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

    leaderboard = _leaderboard_payload(session, redis, game_session.game_id, rotating_scope(now))
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
            "created_at": award.created_at.isoformat(),
        }

    health = session_source_health(session, game_session)
    data = {
        "state": state,
        "closes_at": rnd.scheduled_closes_at.isoformat() if rnd is not None and rnd.scheduled_closes_at else None,
        "rules": overlay_rules_view(rnd.rules_snapshot if rnd is not None else None),
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
        "award_status": award_status_for(state),
        "projection_fresh_at": now.isoformat(),
        "layout_version": 1,
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


def _leaderboard_payload(session: Session, redis: Any, game_id: UUID, scope: PeriodType) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "scope": scope.value,
        "period_id": None,
        "status": None,
        "label": SCOPE_TITLES[scope],
        "entries": [],
    }
    status_rank = case(
        (LeaderboardPeriod.status == PeriodStatus.OPEN.value, 0),
        (LeaderboardPeriod.status == PeriodStatus.CLOSING.value, 1),
        else_=2,
    )
    period = session.scalar(
        select(LeaderboardPeriod)
        .where(
            LeaderboardPeriod.game_id == game_id,
            LeaderboardPeriod.period_type == scope.value,
        )
        .order_by(status_rank, LeaderboardPeriod.starts_at.desc())
    )
    if period is None:
        return payload
    payload["period_id"] = str(period.id)
    payload["status"] = period.status
    payload["label"] = f"{SCOPE_TITLES[scope]} · {period.local_identity}"
    if not redis_available(redis):
        payload["status"] = "Refreshing"
        return payload
    entries = []
    for player_id, points, rank in top_n(redis, game_id=game_id, period_id=period.id, limit=10):
        player = session.get(Player, player_id)
        entries.append(
            {
                "rank": rank,
                "player_id": str(player_id),
                "display_name": sanitize_name(player.display_name if player else "player"),
                "points": points,
            }
        )
    payload["entries"] = entries
    return payload


def _split_recent(item: str) -> dict[str, str]:
    player_id, _, name = item.partition(":")
    return {"player_id": player_id, "name": sanitize_name(name or "player")}
