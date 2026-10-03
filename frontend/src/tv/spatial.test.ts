import { describe, expect, it } from "vitest";

import { pickNext, type Box } from "./spatial";

const tile = (column: number, row: number, shift = 0): Box => ({
  left: column * 320 + shift,
  top: row * 300,
  width: 300,
  height: 200,
});

describe("pickNext", () => {
  const rows = [tile(0, 0), tile(1, 0), tile(2, 0), tile(0, 1, 150), tile(1, 1, 150)];

  it("moves within a row", () => {
    expect(pickNext(rows[0]!, rows, "right")).toBe(1);
    expect(pickNext(rows[1]!, rows, "left")).toBe(0);
    expect(pickNext(rows[2]!, rows, "right")).toBe(-1);
  });

  it("moves to the closest tile of the next row", () => {
    // Below tile 2 (x 640–940) the closest one is tile 4 (x 470–770).
    expect(pickNext(rows[2]!, rows, "down")).toBe(4);
    expect(pickNext(rows[0]!, rows, "down")).toBe(3);
    expect(pickNext(rows[4]!, rows, "up")).toBe(1);
    expect(pickNext(rows[0]!, rows, "up")).toBe(-1);
  });

  it("prefers the nearer row over a closer column further away", () => {
    const boxes = [tile(0, 0), tile(5, 1), tile(0, 2)];
    expect(pickNext(boxes[0]!, boxes, "down")).toBe(1);
  });
});
