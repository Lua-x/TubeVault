/**
 * Spatial navigation for remote controls: the arrow keys move the focus to the
 * nearest element in that direction, like on Apple TV or Android TV.
 */

export type Direction = "up" | "down" | "left" | "right";

export interface Box {
  left: number;
  top: number;
  width: number;
  height: number;
}

const KEYS: Record<string, Direction> = {
  ArrowUp: "up",
  ArrowDown: "down",
  ArrowLeft: "left",
  ArrowRight: "right",
};

export function directionOf(key: string): Direction | null {
  return KEYS[key] ?? null;
}

const overlaps = (a0: number, a1: number, b0: number, b1: number) => a0 < b1 && b0 < a1;

/**
 * Index of the box to move to, or -1 if there is none in that direction.
 *
 * Sideways only moves within the same row (boxes that overlap vertically) and takes the
 * closest one. Up and down go to the nearest row first, then to the box closest
 * horizontally – so moving down from a long row lands right below, not far away.
 */
export function pickNext(from: Box, boxes: Box[], direction: Direction): number {
  const fromRight = from.left + from.width;
  const fromBottom = from.top + from.height;
  const fromCenterX = from.left + from.width / 2;
  let best = -1;
  let bestMain = Infinity;
  let bestCross = Infinity;
  boxes.forEach((box, index) => {
    const right = box.left + box.width;
    const bottom = box.top + box.height;
    let main: number;
    let cross: number;
    if (direction === "left" || direction === "right") {
      if (!overlaps(from.top, fromBottom, box.top, bottom)) return;
      main = direction === "right" ? box.left - fromRight : from.left - right;
      cross = Math.abs(box.top - from.top);
    } else {
      main = direction === "down" ? box.top - fromBottom : from.top - bottom;
      cross = Math.abs(box.left + box.width / 2 - fromCenterX);
    }
    // Only what really lies in that direction (a little overlap is fine).
    if (main < -Math.min(from.width, from.height) / 4) return;
    const sameRow = Math.abs(main - bestMain) < 24;
    if (main < bestMain - 24 || (sameRow && cross < bestCross)) {
      best = index;
      bestMain = Math.min(main, bestMain);
      bestCross = cross;
    }
  });
  return best;
}
