import { describe, expect, it } from "vitest";

import {
  compatibleSlot,
  indexesFor,
  landingTranslateX,
  layoutV1Tiles,
  STRIP_LENGTH,
} from "../../src/animation/layout";
import { estimateOffsetMs, formatCountdown, remainingMs } from "../../src/state/clock";
import { applySnapshot, initialOverlayState } from "../../src/state/reducer";
import { rankMoves } from "../../src/state/ranks";
import { safeText } from "../../src/state/sanitize";
import { snapshot } from "../fixtures/snapshots";

describe("strip layout", () => {
  it("uses 19/19/2 tiles", () => {
    const tiles = layoutV1Tiles();
    expect(tiles).toHaveLength(STRIP_LENGTH);
    expect(tiles.filter((tile) => tile === "red")).toHaveLength(19);
    expect(tiles.filter((tile) => tile === "green")).toHaveLength(19);
    expect(tiles.filter((tile) => tile === "gold")).toHaveLength(2);
  });

  it("lands each color on a matching slot", () => {
    for (const color of ["red", "gold", "green"] as const) {
      const slot = compatibleSlot(color, 0);
      expect(layoutV1Tiles()[slot]).toBe(color);
      expect(indexesFor(color)).toContain(slot);
    }
  });

  it("computes a finite landing translation", () => {
    const x = landingTranslateX({ viewportWidth: 1920, targetSlot: indexesFor("gold")[0] });
    expect(Number.isFinite(x)).toBe(true);
  });
});

describe("snapshot reducer", () => {
  it("rejects older sequences on the same session", () => {
    const first = applySnapshot(initialOverlayState(false), snapshot({ snapshot_sequence: 5 }), 1_000);
    const second = applySnapshot(first.state, snapshot({ snapshot_sequence: 4 }), 1_100);
    expect(second.accepted).toBe(false);
    expect(second.state.lastSequence).toBe(5);
  });

  it("accepts a new session even with a lower sequence", () => {
    const first = applySnapshot(initialOverlayState(false), snapshot({ snapshot_sequence: 9 }), 1_000);
    const next = applySnapshot(
      first.state,
      snapshot({ snapshot_sequence: 1, session_id: "session-2" }),
      1_200,
    );
    expect(next.accepted).toBe(true);
    expect(next.sessionChanged).toBe(true);
  });
});

describe("clock and sanitization", () => {
  it("estimates offset from receive time", () => {
    const offset = estimateOffsetMs("2026-10-04T08:00:10.000Z", Date.parse("2026-10-04T08:00:11.000Z"));
    expect(offset).toBe(-1000);
  });

  it("formats remaining countdown", () => {
    const remaining = remainingMs("2026-10-04T08:00:30.000Z", 0, Date.parse("2026-10-04T08:00:10.000Z"));
    expect(formatCountdown(remaining)).toBe("0:20");
  });

  it("strips unsafe characters from names", () => {
    expect(safeText("<script>Ada\u0000</script>", 24)).toBe("scriptAda/script");
  });
});

describe("rank movement", () => {
  it("does not invent arrows when the scope changes", () => {
    const moves = rankMoves(
      { scope: "weekly", periodId: "a", entries: [{ rank: 1, player_id: "p1" }] },
      { scope: "daily", periodId: "b", entries: [{ rank: 2, player_id: "p1" }] },
    );
    expect(moves[0].direction).toBe("none");
  });

  it("compares consecutive boards of the same period", () => {
    const moves = rankMoves(
      { scope: "weekly", periodId: "a", entries: [{ rank: 2, player_id: "p1" }] },
      { scope: "weekly", periodId: "a", entries: [{ rank: 1, player_id: "p1" }] },
    );
    expect(moves[0].direction).toBe("up");
  });
});
