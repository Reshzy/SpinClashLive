export interface SnapshotEnvelope {
  schema_version: number;
  type: string;
  session_id: string;
  round_id: string | null;
  snapshot_sequence: number;
  server_time: string;
  data: SnapshotData;
}

export interface SnapshotData {
  state: string;
  closes_at: string | null;
  rules: {
    rewards: Record<string, number>;
    weights?: Record<string, number>;
    bonus?: string;
    gold_bonus_reward?: number | null;
    percentages?: Record<string, number>;
  };
  counts: Record<string, number>;
  recent_players: Record<string, Array<{ player_id: string; name: string }>>;
  leaderboard: {
    scope: string;
    period_id: string | null;
    status?: string | null;
    label?: string | null;
    entries: Array<{ rank: number; player_id: string; display_name: string; points: number }>;
  };
  recent_results: string[];
  source_status: string;
  animation_plan: AnimationPlan | null;
  lookup?: Array<Record<string, unknown>>;
  ceremony?: Record<string, unknown> | null;
  award_status?: string;
  projection_fresh_at?: string | null;
  paused?: boolean;
  mode?: string;
  source_mode?: string;
  round_number?: number | null;
  next_bonus?: string;
  next_gold_bonus_reward?: number;
  help?: Record<string, unknown>;
  truncated?: boolean;
}

export interface AnimationPlan {
  animation_id: string;
  starts_at: string;
  ends_at: string;
  duration_s: number;
  layout_version: number;
  target_color: "red" | "gold" | "green";
  target_slot: number;
  target_offset: number;
}

export type ConnectionState = "connecting" | "live" | "recovering";

export interface OverlayState {
  connection: ConnectionState;
  snapshot: SnapshotEnvelope | null;
  lastSequence: number;
  sessionId: string | null;
  clockOffsetMs: number;
  reducedMotion: boolean;
}

export const STATUS_COPY: Record<string, string> = {
  waiting: "Waiting for round",
  open: "Predictions open",
  draining: "Picks closing",
  locked: "Picks locked",
  spinning: "Result incoming",
  result: "Recent results",
  settling: "Updating scores",
  settled: "Points earned",
  cooldown: "Next round soon",
  cancelled: "Round cancelled",
};
