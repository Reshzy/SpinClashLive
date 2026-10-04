const SECRET_KEY = "color-rush-overlay-secret";

export function readAndStripFragment(): string {
  const hash = window.location.hash.replace(/^#/, "").trim();
  if (hash) {
    sessionStorage.setItem(SECRET_KEY, hash);
    const url = new URL(window.location.href);
    url.hash = "";
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
  }
  return sessionStorage.getItem(SECRET_KEY) || hash;
}

export function clearStoredSecret(): void {
  sessionStorage.removeItem(SECRET_KEY);
}

export async function exchangeWsTicket(secret: string): Promise<string> {
  const response = await fetch("/api/v1/overlay/ws-ticket", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secret}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  if (!response.ok) {
    throw new Error("overlay ticket rejected");
  }
  const payload = (await response.json()) as { ticket?: string };
  if (!payload.ticket) {
    throw new Error("overlay ticket missing");
  }
  return payload.ticket;
}
