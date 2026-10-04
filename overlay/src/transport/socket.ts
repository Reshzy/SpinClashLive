export interface OverlaySocketOptions {
  onSnapshot: (raw: unknown, receivedAtMs: number) => void;
  onStatus: (status: "connecting" | "live" | "recovering") => void;
  staleMs?: number;
}

export function connectOverlaySocket(getTicket: () => Promise<string>, options: OverlaySocketOptions): () => void {
  let stopped = false;
  let socket: WebSocket | null = null;
  let staleTimer: number | undefined;
  let attempt = 0;
  const staleMs = options.staleMs ?? 2000;

  const clearStale = () => {
    if (staleTimer !== undefined) {
      window.clearTimeout(staleTimer);
      staleTimer = undefined;
    }
  };

  const armStale = () => {
    clearStale();
    staleTimer = window.setTimeout(() => {
      options.onStatus("recovering");
      socket?.close();
    }, staleMs);
  };

  const backoffMs = () => {
    const base = Math.min(15_000, 1000 * 2 ** attempt);
    const jitter = Math.floor(Math.random() * 250);
    attempt += 1;
    return base + jitter;
  };

  const open = async () => {
    if (stopped) {
      return;
    }
    options.onStatus(attempt === 0 ? "connecting" : "recovering");
    let ticket: string;
    try {
      ticket = await getTicket();
    } catch {
      window.setTimeout(open, backoffMs());
      return;
    }
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    socket = new WebSocket(`${protocol}://${window.location.host}/ws/v1/overlay`);
    socket.addEventListener("open", () => {
      socket?.send(JSON.stringify({ ticket }));
    });
    socket.addEventListener("message", (event) => {
      attempt = 0;
      armStale();
      let parsed: unknown;
      try {
        parsed = JSON.parse(String(event.data));
      } catch {
        return;
      }
      options.onSnapshot(parsed, Date.now());
    });
    socket.addEventListener("close", () => {
      clearStale();
      if (!stopped) {
        options.onStatus("recovering");
        window.setTimeout(open, backoffMs());
      }
    });
    socket.addEventListener("error", () => {
      socket?.close();
    });
  };

  void open();
  return () => {
    stopped = true;
    clearStale();
    socket?.close();
  };
}
