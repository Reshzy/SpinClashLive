export const STRIP_LENGTH = 40;
export const GOLD_INDEXES = [9, 28] as const;
export const TILE_GAP = 8;
export const TILE_WIDTH = 96;
export const STRIP_COPIES = 8;

export type ColorName = "red" | "gold" | "green";

export function layoutV1Tiles(): ColorName[] {
  return Array.from({ length: STRIP_LENGTH }, (_, index) => {
    if (index === GOLD_INDEXES[0] || index === GOLD_INDEXES[1]) {
      return "gold";
    }
    return index % 2 === 0 ? "red" : "green";
  });
}

export function indexesFor(color: ColorName): number[] {
  return layoutV1Tiles()
    .map((tile, index) => (tile === color ? index : -1))
    .filter((index) => index >= 0);
}

export function compatibleSlot(color: ColorName, requestedSlot: number): number {
  const tiles = layoutV1Tiles();
  if (requestedSlot >= 0 && requestedSlot < tiles.length && tiles[requestedSlot] === color) {
    return requestedSlot;
  }
  return indexesFor(color)[0];
}

export function landingTranslateX(options: {
  viewportWidth: number;
  targetSlot: number;
  copyIndex?: number;
  tileWidth?: number;
}): number {
  const tileWidth = (options.tileWidth ?? TILE_WIDTH) + TILE_GAP;
  const copy = options.copyIndex ?? Math.floor(STRIP_COPIES / 2);
  const targetCenter = (copy * STRIP_LENGTH + options.targetSlot + 0.5) * tileWidth;
  return options.viewportWidth / 2 - targetCenter;
}

export function spinStartTranslateX(landingX: number, cycles = 3): number {
  return landingX + cycles * STRIP_LENGTH * (TILE_WIDTH + TILE_GAP);
}
