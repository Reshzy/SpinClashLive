import { estimateOffsetMs } from "./clock";
import type { OverlayState, SnapshotEnvelope } from "./types";

export function initialOverlayState(reducedMotion: boolean): OverlayState {
  return {
    connection: "connecting",
    snapshot: null,
    lastSequence: -1,
    sessionId: null,
    clockOffsetMs: 0,
    reducedMotion,
  };
}

export interface ApplyResult {
  state: OverlayState;
  accepted: boolean;
  sessionChanged: boolean;
}

export function applySnapshot(
  prev: OverlayState,
  envelope: SnapshotEnvelope,
  receivedAtMs: number,
  sentAtMs?: number,
): ApplyResult {
  if (envelope.type !== "snapshot") {
    return { state: prev, accepted: false, sessionChanged: false };
  }
  const sessionChanged = prev.sessionId !== null && prev.sessionId !== envelope.session_id;
  if (!sessionChanged && envelope.snapshot_sequence < prev.lastSequence) {
    return { state: prev, accepted: false, sessionChanged: false };
  }
  return {
    accepted: true,
    sessionChanged,
    state: {
      ...prev,
      connection: "live",
      snapshot: envelope,
      lastSequence: envelope.snapshot_sequence,
      sessionId: envelope.session_id,
      clockOffsetMs: estimateOffsetMs(envelope.server_time, receivedAtMs, sentAtMs),
    },
  };
}

export function markRecovering(prev: OverlayState): OverlayState {
  return { ...prev, connection: "recovering" };
}

export function markConnecting(prev: OverlayState): OverlayState {
  return { ...prev, connection: "connecting", lastSequence: -1 };
}
