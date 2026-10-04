export interface RankMove {
  playerId: string;
  direction: "up" | "down" | "same" | "none";
}

export interface BoardSnapshot {
  scope: string;
  periodId: string | null;
  entries: Array<{ rank: number; player_id: string }>;
}

export function rankMoves(previous: BoardSnapshot | null, next: BoardSnapshot): RankMove[] {
  if (
    previous === null ||
    previous.scope !== next.scope ||
    previous.periodId !== next.periodId ||
    previous.periodId === null
  ) {
    return next.entries.map((entry) => ({ playerId: entry.player_id, direction: "none" as const }));
  }
  const prior = new Map(previous.entries.map((entry) => [entry.player_id, entry.rank]));
  return next.entries.map((entry) => {
    const before = prior.get(entry.player_id);
    if (before === undefined) {
      return { playerId: entry.player_id, direction: "none" as const };
    }
    if (entry.rank < before) {
      return { playerId: entry.player_id, direction: "up" as const };
    }
    if (entry.rank > before) {
      return { playerId: entry.player_id, direction: "down" as const };
    }
    return { playerId: entry.player_id, direction: "same" as const };
  });
}
