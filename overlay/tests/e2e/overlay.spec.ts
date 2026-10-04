import { expect, test, type Page } from "@playwright/test";

import { compatibleSlot, indexesFor } from "../../src/animation/layout";
import { snapshot } from "../fixtures/snapshots";

async function openOverlay(page: Page): Promise<{ send: (payload: unknown) => void }> {
  await page.route("**/api/v1/overlay/ws-ticket", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ticket: "short-lived", expires_in: 120, ws_path: "/ws/v1/overlay" }),
    });
  });
  const handle = { send(_payload: unknown) {} };
  let connected = false;
  await page.routeWebSocket(/\/ws\/v1\/overlay/, (ws) => {
    connected = true;
    handle.send = (payload: unknown) => {
      ws.send(JSON.stringify(payload));
    };
  });
  await page.goto("/?reduced-motion=1#overlay-secret");
  await expect.poll(() => connected).toBeTruthy();
  return handle;
}

test("open state at 1080p", async ({ page }) => {
  const handle = await openOverlay(page);
  handle.send(snapshot({ data: { state: "open", award_status: "none" } }));
  await expect(page.locator("#status")).toHaveText("Predictions open");
  await expect(page.locator("#help")).toContainText("!red");
  await expect(page.locator("#odds")).toContainText("47.5%");
  await page.screenshot({ path: "tests/e2e/screenshots/open-1080.png", fullPage: true });
});

test("spinning and gold result landing", async ({ page }) => {
  const slot = compatibleSlot("gold", indexesFor("gold")[0]);
  const now = Date.now();
  const plan = {
    animation_id: "anim-gold",
    starts_at: new Date(now - 6000).toISOString(),
    ends_at: new Date(now - 100).toISOString(),
    duration_s: 6,
    layout_version: 1,
    target_color: "gold" as const,
    target_slot: slot,
    target_offset: 0,
  };
  const handle = await openOverlay(page);
  handle.send(
    snapshot({
      snapshot_sequence: 2,
      data: { state: "spinning", animation_plan: plan, award_status: "pending" },
    }),
  );
  await expect(page.locator("#status")).toHaveText("Result incoming");
  await page.screenshot({ path: "tests/e2e/screenshots/spinning-1080.png", fullPage: true });
  handle.send(
    snapshot({
      snapshot_sequence: 3,
      data: {
        state: "result",
        animation_plan: plan,
        award_status: "pending",
        counts: { red: 10, gold: 2, green: 8 },
      },
    }),
  );
  await expect(page.locator("#award-status")).toHaveText("Updating scores");
  const error = await page.locator("#marker").getAttribute("data-align-error");
  expect(Number(error ?? "99")).toBeLessThan(8);
  await page.screenshot({ path: "tests/e2e/screenshots/gold-result-1080.png", fullPage: true });
});

test("reload during settling and unsafe names", async ({ page }) => {
  const handle = await openOverlay(page);
  handle.send(
    snapshot({
      data: {
        state: "settling",
        award_status: "pending",
        recent_players: {
          red: [{ player_id: "x", name: "<img src=x onerror=alert(1)>verylongplayernameyes" }],
          gold: [],
          green: [],
        },
      },
    }),
  );
  await expect(page.locator("#status")).toHaveText("Updating scores");
  await expect(page.locator('[data-names="red"] li')).toHaveCount(1);
  await expect(page.locator('[data-names="red"] li')).not.toContainText("<img");
  await page.reload();
  await page.waitForTimeout(200);
  handle.send(snapshot({ snapshot_sequence: 8, data: { state: "settling", award_status: "pending" } }));
  await expect(page.locator("#status")).toHaveText("Updating scores");
});

test("old snapshot is ignored and empty board is intentional", async ({ page }) => {
  const handle = await openOverlay(page);
  handle.send(snapshot({ snapshot_sequence: 10, data: { state: "locked", counts: { red: 0, gold: 0, green: 0 } } }));
  await expect(page.locator("#status")).toHaveText("Picks locked");
  handle.send(snapshot({ snapshot_sequence: 2, data: { state: "open" } }));
  await expect(page.locator("#status")).toHaveText("Picks locked");
  handle.send(
    snapshot({
      snapshot_sequence: 11,
      data: {
        state: "open",
        counts: { red: 0, gold: 0, green: 0 },
        recent_players: { red: [], gold: [], green: [] },
      },
    }),
  );
  await expect(page.locator("#empty-picks")).toBeVisible();
});

test("period rollover label and 720p frame", async ({ page }) => {
  const handle = await openOverlay(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  handle.send(
    snapshot({
      data: {
        leaderboard: {
          scope: "daily",
          period_id: "period-2",
          status: "closing",
          label: "Daily · 2026-10-03",
          entries: [{ rank: 1, player_id: "p9", display_name: "Cara", points: 0 }],
        },
      },
    }),
  );
  await expect(page.locator("#board-title")).toContainText("Daily");
  await expect(page.locator("#board-status")).toHaveText("closing");
  await page.screenshot({ path: "tests/e2e/screenshots/rollover-720.png", fullPage: true });
});

test("cancelled and draining copy", async ({ page }) => {
  const handle = await openOverlay(page);
  handle.send(snapshot({ snapshot_sequence: 1, data: { state: "draining" } }));
  await expect(page.locator("#status")).toHaveText("Picks closing");
  handle.send(snapshot({ snapshot_sequence: 2, data: { state: "cancelled", award_status: "cancelled" } }));
  await expect(page.locator("#status")).toHaveText("Round cancelled");
});
