import gsap from "gsap";

import {
  compatibleSlot,
  landingTranslateX,
  layoutV1Tiles,
  spinStartTranslateX,
  STRIP_COPIES,
  STRIP_LENGTH,
} from "./layout";
import type { AnimationPlan } from "../state/types";
import { animationProgress } from "../state/clock";

let timeline: gsap.core.Timeline | null = null;
let lastAnimationId = "";

export function mountStrip(root: HTMLElement): void {
  root.replaceChildren();
  const tiles = layoutV1Tiles();
  for (let copy = 0; copy < STRIP_COPIES; copy += 1) {
    for (const color of tiles) {
      const tile = document.createElement("div");
      tile.className = `strip-tile ${color}`;
      tile.dataset.color = color;
      root.append(tile);
    }
  }
}

export function disposeStrip(): void {
  timeline?.kill();
  timeline = null;
  lastAnimationId = "";
}

export function alignmentErrorPx(tile: Element, marker: Element): number {
  const tileBox = tile.getBoundingClientRect();
  const markerBox = marker.getBoundingClientRect();
  const tileCenter = (tileBox.left + tileBox.right) / 2;
  const markerCenter = (markerBox.left + markerBox.right) / 2;
  return Math.abs(tileCenter - markerCenter);
}

export function targetTile(root: HTMLElement, slot: number): HTMLElement | null {
  const copy = Math.floor(STRIP_COPIES / 2);
  return root.children.item(copy * STRIP_LENGTH + slot) as HTMLElement | null;
}

export function applyStripPlan(options: {
  strip: HTMLElement;
  marker: HTMLElement;
  plan: AnimationPlan | null;
  state: string;
  offsetMs: number;
  reducedMotion: boolean;
  viewportWidth: number;
}): number | null {
  const { strip, marker, plan, state, offsetMs, reducedMotion, viewportWidth } = options;
  if (plan === null) {
    if (state !== "spinning" && state !== "result" && state !== "settling" && state !== "settled") {
      disposeStrip();
    }
    return null;
  }
  const slot = compatibleSlot(plan.target_color, plan.target_slot);
  const landingX = landingTranslateX({ viewportWidth, targetSlot: slot });
  const startX = spinStartTranslateX(landingX);
  const tile = targetTile(strip, slot);
  for (const node of strip.querySelectorAll(".is-target")) {
    node.classList.remove("is-target");
  }
  tile?.classList.add("is-target");

  const progress = animationProgress(plan, offsetMs);
  const remainingS = Math.max(0, ((1 - progress) * plan.duration_s));
  const spinning = state === "spinning" && remainingS > 0.04;

  if (!spinning || reducedMotion) {
    timeline?.kill();
    timeline = null;
    gsap.set(strip, { x: landingX });
    lastAnimationId = plan.animation_id;
    return tile ? alignmentErrorPx(tile, marker) : null;
  }

  if (lastAnimationId === plan.animation_id && timeline) {
    return null;
  }
  timeline?.kill();
  const currentX = startX + (landingX - startX) * progress;
  gsap.set(strip, { x: currentX });
  timeline = gsap.timeline({
    onComplete: () => {
      gsap.set(strip, { x: landingX });
    },
  });
  timeline.to(strip, { x: landingX, duration: remainingS, ease: "power2.out" });
  lastAnimationId = plan.animation_id;
  return null;
}
