from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True, slots=True)
class RankKey:
    points: int
    player_id: UUID


def rank_key(points: int, player_id: UUID) -> RankKey:
    return RankKey(points=points, player_id=player_id)


def sort_entries(entries: Sequence[RankKey]) -> list[RankKey]:
    return sorted(entries, key=lambda item: (-item.points, item.player_id))


def ordinal_ranks(entries: Sequence[RankKey]) -> list[tuple[int, RankKey]]:
    ordered = sort_entries(entries)
    return [(index + 1, item) for index, item in enumerate(ordered)]
