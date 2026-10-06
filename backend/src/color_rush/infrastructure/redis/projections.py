from __future__ import annotations

from json import dumps, loads
from typing import Any, cast
from uuid import UUID

from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from color_rush.domain.enums import Color
from color_rush.infrastructure.persistence.models import (
    LeaderboardPeriod,
    LeaderboardScore,
    Pick,
    Player,
    Round,
)

STREAM_GAME = "outbox.game"
STREAM_PROJECTIONS = "outbox.projections"
STREAM_EVENTS = STREAM_GAME
STREAM_DLQ = "outbox.dlq"
GROUP_PROJECTION = "projection"
GROUP_SNAPSHOT = "snapshot"
OUTBOX_STREAMS = (STREAM_GAME, STREAM_PROJECTIONS)
MAX_DELIVERIES = 8


def connect_redis(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


def redis_available(client: Redis | None) -> bool:
    if client is None:
        return False
    try:
        return bool(client.ping())
    except RedisError:
        return False


def lb_key(game_id: UUID, period_id: UUID, generation: int) -> str:
    return f"game:{game_id}:lb:{period_id}:generation:{generation}"


def ver_key(game_id: UUID, period_id: UUID, player_id: UUID) -> str:
    return f"game:{game_id}:lb:{period_id}:ver:{player_id}"


def gen_key(game_id: UUID, period_id: UUID) -> str:
    return f"game:{game_id}:lb:{period_id}:active_generation"


def counts_key(game_id: UUID, round_id: UUID) -> str:
    return f"game:{game_id}:round:{round_id}:counts"


def recent_key(game_id: UUID, round_id: UUID, color: str) -> str:
    return f"game:{game_id}:round:{round_id}:recent:{color}"


def history_key(game_id: UUID) -> str:
    return f"game:{game_id}:history"


def snapshot_key(game_id: UUID) -> str:
    return f"game:{game_id}:overlay:snapshot"


def seq_key(game_id: UUID) -> str:
    return f"game:{game_id}:snapshot_seq"


def lookup_key(game_id: UUID) -> str:
    return f"game:{game_id}:lookup"


def encoded_score(points: int) -> int:
    return -int(points)


def decoded_score(stored: float) -> int:
    return -int(stored)


def write_score(
    client: Redis,
    *,
    game_id: UUID,
    period_id: UUID,
    player_id: UUID,
    points: int,
    score_version: int,
    generation: int | None = None,
) -> bool:
    active = int(client.get(gen_key(game_id, period_id)) or 1)
    generation = generation or active
    version_name = ver_key(game_id, period_id, player_id)
    current = int(client.get(version_name) or 0)
    if score_version < current:
        return False
    client.set(version_name, score_version)
    client.zadd(lb_key(game_id, period_id, generation), {str(player_id): encoded_score(points)})
    return True


def top_n(
    client: Redis,
    *,
    game_id: UUID,
    period_id: UUID,
    limit: int = 10,
) -> list[tuple[UUID, int, int]]:
    active = int(client.get(gen_key(game_id, period_id)) or 1)
    raw_rows = client.zrange(lb_key(game_id, period_id, active), 0, limit - 1, withscores=True)
    rows = cast(list[tuple[Any, Any]], raw_rows)
    result: list[tuple[UUID, int, int]] = []
    for index, item in enumerate(rows, start=1):
        member, score = item
        result.append((UUID(str(member)), decoded_score(float(score)), index))
    return result


def rank_of(client: Redis, *, game_id: UUID, period_id: UUID, player_id: UUID) -> int | None:
    active = int(client.get(gen_key(game_id, period_id)) or 1)
    rank = client.zrank(lb_key(game_id, period_id, active), str(player_id))
    if not isinstance(rank, int):
        return None
    return rank + 1


def project_round_counts(client: Redis, session: Session, game_id: UUID, round_id: UUID) -> dict[str, int]:
    picks = list(session.scalars(select(Pick).where(Pick.round_id == round_id)))
    counts = {color.value: 0 for color in Color}
    recent: dict[str, list[str]] = {color.value: [] for color in Color}
    ordered = sorted(picks, key=lambda item: item.updated_at, reverse=True)
    for pick in ordered:
        counts[pick.choice] = counts.get(pick.choice, 0) + 1
        if len(recent[pick.choice]) < 10:
            player = session.get(Player, pick.player_id)
            name = sanitize_name(player.display_name if player else "player")
            recent[pick.choice].append(f"{pick.player_id}:{name}")
    client.hset(counts_key(game_id, round_id), mapping={key: str(value) for key, value in counts.items()})
    for color, names in recent.items():
        client.delete(recent_key(game_id, round_id, color))
        if names:
            client.rpush(recent_key(game_id, round_id, color), *names)
    return counts


def append_history(client: Redis, game_id: UUID, color: str) -> None:
    client.lpush(history_key(game_id), color)
    client.ltrim(history_key(game_id), 0, 19)


def recent_history(client: Redis, game_id: UUID) -> list[str]:
    return [str(item) for item in client.lrange(history_key(game_id), 0, 19)]


def rebuild_all_leaderboards(client: Redis, session: Session, game_id: UUID) -> dict[str, int]:
    generations: dict[str, int] = {}
    for period in active_periods(session, game_id):
        generations[str(period.id)] = rebuild_leaderboard(client, session, game_id, period.id)
    return generations


def rebuild_leaderboard(client: Redis, session: Session, game_id: UUID, period_id: UUID) -> int:
    current = int(client.get(gen_key(game_id, period_id)) or 1)
    shadow = current + 1
    scores = list(session.scalars(select(LeaderboardScore).where(LeaderboardScore.period_id == period_id)))
    pipe = client.pipeline()
    key = lb_key(game_id, period_id, shadow)
    pipe.delete(key)
    for row in scores:
        pipe.zadd(key, {str(row.player_id): encoded_score(row.points)})
        pipe.set(ver_key(game_id, period_id, row.player_id), row.score_version)
    pipe.set(gen_key(game_id, period_id), shadow)
    pipe.delete(lb_key(game_id, period_id, current))
    pipe.execute()
    return shadow


def publish_outbox(client: Redis, *, event_id: str, event_type: str, payload: dict[str, Any], aggregate_id: str) -> str:
    fields = {
        "event_id": event_id,
        "event_type": event_type,
        "aggregate_id": aggregate_id,
        "payload": dumps(payload),
    }
    last = "0-0"
    for stream in OUTBOX_STREAMS:
        last = str(client.xadd(stream, fields))  # type: ignore[arg-type]
    return last


def ensure_groups(client: Redis) -> None:
    for stream in OUTBOX_STREAMS:
        for group in (GROUP_PROJECTION, GROUP_SNAPSHOT):
            try:
                client.xgroup_create(stream, group, id="0", mkstream=True)
            except RedisError:
                continue


def ack_event(client: Redis, group: str, entry_id: str, stream: str = STREAM_EVENTS) -> None:
    client.xack(stream, group, entry_id)


def dead_letter(client: Redis, *, event_id: str, reason: str, payload: str) -> None:
    client.xadd(STREAM_DLQ, {"event_id": event_id, "reason": reason, "payload": payload})


def recover_pending(
    client: Redis,
    *,
    group: str,
    consumer: str = "recovery",
    min_idle_ms: int = 5_000,
    max_deliveries: int = MAX_DELIVERIES,
) -> int:
    recovered = 0
    for stream in OUTBOX_STREAMS:
        try:
            pending = client.xpending_range(stream, group, min="-", max="+", count=50)
        except RedisError:
            continue
        for item in pending:
            msg_id = str(item["message_id"])
            deliveries = int(item.get("times_delivered") or 1)
            if deliveries >= max_deliveries:
                dead_letter(client, event_id=msg_id, reason="max_retries", payload=stream)
                ack_event(client, group, msg_id, stream=stream)
                continue
            claimed = client.xclaim(stream, group, consumer, min_idle_ms, [msg_id])
            if claimed:
                recovered += 1
    return recovered


def consume_group(
    client: Redis,
    *,
    group: str,
    consumer: str,
    count: int = 20,
) -> list[dict[str, str]]:
    ensure_groups(client)
    recover_pending(client, group=group, consumer=consumer)
    events: list[dict[str, str]] = []
    streams = {name: ">" for name in OUTBOX_STREAMS}
    messages = client.xreadgroup(group, consumer, streams, count=count, block=1)  # type: ignore[arg-type]
    rows = cast(list[tuple[str, list[tuple[str, dict[str, Any]]]]], messages or [])
    for stream_name, entries in rows:
        for entry_id, fields in entries:
            events.append(
                {
                    "stream": str(stream_name),
                    "id": str(entry_id),
                    "event_id": str(fields.get("event_id") or ""),
                    "event_type": str(fields.get("event_type") or ""),
                    "payload": str(fields.get("payload") or "{}"),
                }
            )
    return events


def trim_completed(client: Redis, last_id: str) -> None:
    for stream in OUTBOX_STREAMS:
        client.xtrim(stream, minid=last_id, approximate=False)


def store_snapshot(client: Redis, game_id: UUID, payload: dict[str, Any]) -> int:
    seq = int(client.incr(seq_key(game_id)))
    payload["snapshot_sequence"] = seq
    client.set(snapshot_key(game_id), dumps(payload))
    client.publish(f"game:{game_id}:snapshot", dumps(payload))
    return seq


def load_snapshot(client: Redis, game_id: UUID) -> dict[str, Any] | None:
    raw = client.get(snapshot_key(game_id))
    if not raw:
        return None
    data = loads(raw)
    return data if isinstance(data, dict) else None


def push_lookup(client: Redis, game_id: UUID, item: dict[str, Any], *, max_items: int = 20) -> None:
    player_id = str(item.get("player_id"))
    existing = client.lrange(lookup_key(game_id), 0, -1)
    kept = [row for row in existing if loads(row).get("player_id") != player_id]
    kept.insert(0, dumps(item))
    client.delete(lookup_key(game_id))
    if kept[:max_items]:
        client.rpush(lookup_key(game_id), *kept[:max_items])


def list_lookup(client: Redis, game_id: UUID) -> list[dict[str, Any]]:
    return [loads(item) for item in client.lrange(lookup_key(game_id), 0, -1)]


def delete_player_keys(client: Redis, game_id: UUID, player_id: UUID, period_ids: list[UUID]) -> None:
    for period_id in period_ids:
        active = int(client.get(gen_key(game_id, period_id)) or 1)
        client.zrem(lb_key(game_id, period_id, active), str(player_id))
        client.delete(ver_key(game_id, period_id, player_id))


def sanitize_name(name: str) -> str:
    cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in "<>")
    return (cleaned or "player")[:24]


def round_result_color(session: Session, round_id: UUID) -> str | None:
    rnd = session.get(Round, round_id)
    return rnd.result if rnd is not None else None


def active_periods(session: Session, game_id: UUID) -> list[LeaderboardPeriod]:
    return list(session.scalars(select(LeaderboardPeriod).where(LeaderboardPeriod.game_id == game_id)))
