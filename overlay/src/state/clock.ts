export function estimateOffsetMs(serverTime: string, receivedAtMs: number, sentAtMs?: number): number {
  const serverMs = Date.parse(serverTime);
  if (Number.isNaN(serverMs)) {
    return 0;
  }
  const midpoint = sentAtMs === undefined ? receivedAtMs : (sentAtMs + receivedAtMs) / 2;
  return serverMs - midpoint;
}

export function serverNowMs(offsetMs: number, nowMs = Date.now()): number {
  return nowMs + offsetMs;
}

export function remainingMs(closesAt: string | null, offsetMs: number, nowMs = Date.now()): number | null {
  if (!closesAt) {
    return null;
  }
  const closeMs = Date.parse(closesAt);
  if (Number.isNaN(closeMs)) {
    return null;
  }
  return closeMs - serverNowMs(offsetMs, nowMs);
}

export function formatCountdown(ms: number | null): string {
  if (ms === null) {
    return "";
  }
  const clamped = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(clamped / 60);
  const seconds = clamped % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function animationProgress(plan: { starts_at: string; ends_at: string }, offsetMs: number, nowMs = Date.now()): number {
  const start = Date.parse(plan.starts_at);
  const end = Date.parse(plan.ends_at);
  if (Number.isNaN(start) || Number.isNaN(end) || end <= start) {
    return 1;
  }
  const t = serverNowMs(offsetMs, nowMs);
  if (t <= start) {
    return 0;
  }
  if (t >= end) {
    return 1;
  }
  return (t - start) / (end - start);
}
