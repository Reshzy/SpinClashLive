import "@fontsource/outfit/400.css";
import "@fontsource/outfit/700.css";
import "./styles/overlay.css";

import { celebrateGold, clearCelebration } from "./animation/particles";
import { applyStripPlan, disposeStrip, mountStrip } from "./animation/strip";
import { renderOverlay, scaleStage } from "./components/render";
import { applySnapshot, initialOverlayState, markConnecting, markRecovering } from "./state/reducer";
import type { OverlayState, SnapshotEnvelope } from "./state/types";
import { exchangeWsTicket, readAndStripFragment } from "./transport/auth";
import { connectOverlaySocket } from "./transport/socket";

const params = new URLSearchParams(window.location.search);
const transparent = params.get("transparent") === "1";
const reducedMotion =
  params.get("reduced-motion") === "1" || window.matchMedia("(prefers-reduced-motion: reduce)").matches;

if (transparent) {
  document.documentElement.classList.add("transparent");
}

const stageEl = requireElement("stage");
const stripEl = requireElement("strip");
const markerEl = requireElement("marker");
const particlesEl = requireElement("particles");

function requireElement(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (!node) {
    throw new Error(`overlay markup missing: ${id}`);
  }
  return node;
}

mountStrip(stripEl);
scaleStage(stageEl);
window.addEventListener("resize", () => {
  scaleStage(stageEl);
  if (state.snapshot?.data.animation_plan) {
    applyStripPlan({
      strip: stripEl,
      marker: markerEl,
      plan: state.snapshot.data.animation_plan,
      state: state.snapshot.data.state,
      offsetMs: state.clockOffsetMs,
      reducedMotion,
      viewportWidth: stripEl.parentElement?.clientWidth ?? 1920,
    });
  }
});

let state: OverlayState = initialOverlayState(reducedMotion);
let lastGoldId = "";

function paint(): void {
  renderOverlay(state);
  const data = state.snapshot?.data;
  const error = applyStripPlan({
    strip: stripEl,
    marker: markerEl,
    plan: data?.animation_plan ?? null,
    state: data?.state ?? "waiting",
    offsetMs: state.clockOffsetMs,
    reducedMotion,
    viewportWidth: stripEl.parentElement?.clientWidth ?? 1920,
  });
  if (error !== null) {
    markerEl.dataset.alignError = String(Math.round(error));
  }
  const goldResult =
    data?.animation_plan?.target_color === "gold" &&
    data.animation_plan.animation_id !== lastGoldId &&
    ["result", "settling", "settled"].includes(data.state);
  if (goldResult && data.animation_plan) {
    lastGoldId = data.animation_plan.animation_id;
    if (!reducedMotion) {
      celebrateGold(particlesEl, true);
    }
  }
  if (data?.state === "open" || data?.state === "waiting") {
    clearCelebration(particlesEl);
  }
}

function onSnapshot(raw: unknown, receivedAtMs: number): void {
  if (!raw || typeof raw !== "object") {
    return;
  }
  const envelope = raw as SnapshotEnvelope;
  const result = applySnapshot(state, envelope, receivedAtMs);
  if (!result.accepted) {
    return;
  }
  if (result.sessionChanged) {
    disposeStrip();
    mountStrip(stripEl);
    lastGoldId = "";
  }
  state = result.state;
  paint();
}

const secret = readAndStripFragment();
if (!secret) {
  state = markConnecting(state);
  paint();
}

connectOverlaySocket(
  async () => {
    if (!secret) {
      throw new Error("missing overlay secret");
    }
    return exchangeWsTicket(secret);
  },
  {
    onSnapshot,
    onStatus: (status) => {
      state = status === "recovering" ? markRecovering(state) : status === "connecting" ? markConnecting(state) : state;
      if (status === "live") {
        state = { ...state, connection: "live" };
      }
      paint();
    },
  },
);

window.setInterval(() => {
  if (state.snapshot) {
    paint();
  }
}, 200);

window.addEventListener("beforeunload", () => {
  disposeStrip();
  clearCelebration(particlesEl);
});

paint();
