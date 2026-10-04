import type { SnapshotEnvelope } from "../../src/state/types";

export function snapshot(overrides: Partial<SnapshotEnvelope> & { data?: Partial<SnapshotEnvelope["data"]> } = {}): SnapshotEnvelope {
  const data = {
    state: "open",
    closes_at: "2026-10-04T08:00:30.000Z",
    rules: {
      rewards: { red: 2, gold: 14, green: 2 },
      weights: { red: 475, gold: 50, green: 475 },
      bonus: "none",
      percentages: { red: 47.5, gold: 5, green: 47.5 },
    },
    counts: { red: 3, gold: 0, green: 2 },
    recent_players: {
      red: [{ player_id: "p1", name: "Ada" }],
      gold: [],
      green: [{ player_id: "p2", name: "Bea" }],
    },
    leaderboard: {
      scope: "weekly",
      period_id: "period-1",
      status: "open",
      label: "Weekly · 2026-09-28",
      entries: [
        { rank: 1, player_id: "p1", display_name: "Ada", points: 40 },
        { rank: 2, player_id: "p2", display_name: "Bea", points: 20 },
      ],
    },
    recent_results: ["red", "green"],
    source_status: "healthy",
    animation_plan: null,
    lookup: [],
    ceremony: null,
    award_status: "none",
    source_mode: "simulation",
    round_number: 4,
    help: { commands: "!red / !gold / !green" },
    ...overrides.data,
  };
  return {
    schema_version: 1,
    type: "snapshot",
    session_id: "session-1",
    round_id: "round-1",
    snapshot_sequence: 1,
    server_time: "2026-10-04T08:00:10.000Z",
    ...overrides,
    data,
  };
}
