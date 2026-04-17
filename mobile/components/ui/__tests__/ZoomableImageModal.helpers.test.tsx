import {
  clampScale,
  MAX_SCALE,
  MIN_SCALE,
  shouldDismissOnSwipeDown,
  twoFingerDistance,
} from "../zoomable-image-math";

describe("twoFingerDistance", () => {
  it("returns euclidean distance for two touches (3-4-5 triangle)", () => {
    expect(twoFingerDistance([
      { pageX: 0, pageY: 0 },
      { pageX: 3, pageY: 4 },
    ])).toBe(5);
  });

  it("is symmetric in the order of touches", () => {
    const a = twoFingerDistance([
      { pageX: 10, pageY: 10 },
      { pageX: 20, pageY: 30 },
    ]);
    const b = twoFingerDistance([
      { pageX: 20, pageY: 30 },
      { pageX: 10, pageY: 10 },
    ]);
    expect(a).toBeCloseTo(b);
  });

  it("returns 0 when fewer than two touches are present", () => {
    expect(twoFingerDistance([])).toBe(0);
    expect(twoFingerDistance([{ pageX: 0, pageY: 0 }])).toBe(0);
  });

  it("ignores extra touches beyond the first two", () => {
    expect(twoFingerDistance([
      { pageX: 0, pageY: 0 },
      { pageX: 0, pageY: 10 },
      { pageX: 999, pageY: 999 },
    ])).toBe(10);
  });
});

describe("clampScale", () => {
  it("clamps values below the minimum up to MIN_SCALE", () => {
    expect(clampScale(0.1)).toBe(MIN_SCALE);
    expect(clampScale(-5)).toBe(MIN_SCALE);
  });

  it("clamps values above the maximum down to MAX_SCALE", () => {
    expect(clampScale(MAX_SCALE + 5)).toBe(MAX_SCALE);
    expect(clampScale(100)).toBe(MAX_SCALE);
  });

  it("returns the value unchanged inside the range", () => {
    expect(clampScale(1.5)).toBe(1.5);
    expect(clampScale(2.7)).toBe(2.7);
  });

  it("snaps non-finite inputs back to the minimum", () => {
    expect(clampScale(NaN)).toBe(MIN_SCALE);
    expect(clampScale(Number.POSITIVE_INFINITY)).toBe(MIN_SCALE);
  });
});

describe("shouldDismissOnSwipeDown", () => {
  it("dismisses once translateY clears the gate (no velocity needed)", () => {
    expect(shouldDismissOnSwipeDown(200, 0)).toBe(true);
  });

  it("dismisses on a fast flick even below the translate gate", () => {
    expect(shouldDismissOnSwipeDown(50, 1.2)).toBe(true);
  });

  it("does not dismiss on small drift with no velocity", () => {
    expect(shouldDismissOnSwipeDown(30, 0)).toBe(false);
  });

  it("does not dismiss on upward drag (negative translateY)", () => {
    expect(shouldDismissOnSwipeDown(-200, -1.5)).toBe(false);
  });
});
