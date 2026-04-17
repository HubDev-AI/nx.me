/**
 * Pure math helpers for ZoomableImageModal.
 *
 * Lives in its own module so jest-expo can load it without pulling in
 * Reanimated / Worklets (which fail to initialise under the jest
 * runner — see profile.test.tsx for the same pattern).
 */

interface FingerPoint {
  pageX: number;
  pageY: number;
}

/** Clamp bounds for pinch scale — keep the zoom usable but not absurd. */
export const MIN_SCALE = 1;
export const MAX_SCALE = 4;

/** translateY and velocity thresholds that trigger swipe-down dismiss. */
export const SWIPE_DISMISS_TRANSLATE_Y = 120;
export const SWIPE_DISMISS_VELOCITY_Y = 0.8;
export const SWIPE_DISMISS_VELOCITY_MIN_TRAVEL = 32;

/** Distance (px) between the first two active touch points; 0 if fewer than 2. */
export function twoFingerDistance(touches: readonly FingerPoint[]): number {
  if (touches.length < 2) return 0;
  const [a, b] = touches;
  if (!a || !b) return 0;
  const dx = a.pageX - b.pageX;
  const dy = a.pageY - b.pageY;
  return Math.sqrt(dx * dx + dy * dy);
}

/** Clamp scale into the usable pinch range. */
export function clampScale(scale: number): number {
  if (!isFinite(scale)) return MIN_SCALE;
  return Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));
}

/**
 * Swipe-down dismiss predicate — fires when translateY clears the gate
 * OR velocity is high enough that the user clearly flicked down.
 */
export function shouldDismissOnSwipeDown(
  translateY: number,
  velocityY: number,
): boolean {
  if (translateY >= SWIPE_DISMISS_TRANSLATE_Y) return true;
  if (
    velocityY >= SWIPE_DISMISS_VELOCITY_Y &&
    translateY > SWIPE_DISMISS_VELOCITY_MIN_TRAVEL
  ) {
    return true;
  }
  return false;
}
