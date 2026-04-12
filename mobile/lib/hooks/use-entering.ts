/**
 * Reduced-motion-aware entering animation factory.
 *
 * Replaces call sites like `FadeInDown.delay(N).duration(400)` so that
 * users who have opted into reduced motion get a plain opacity fade
 * without vertical translation or long delays. Without this gate,
 * cascade entrances still slide & wait even when the OS requests
 * reduced motion — a §1-Accessibility violation.
 */
import { useCallback } from "react";
import {
  FadeIn,
  FadeInDown,
  useReducedMotion,
  type EntryAnimationsValues,
  type EntryExitAnimationFunction,
} from "react-native-reanimated";

/**
 * `type EnteringAnim` matches the shape of Reanimated entering animations
 * (both `FadeIn.X()` and `FadeInDown.X()` extend the base layout animation).
 */
type EnteringAnim =
  | ReturnType<typeof FadeIn.duration>
  | ReturnType<typeof FadeInDown.duration>
  | EntryExitAnimationFunction
  | ((values: EntryAnimationsValues) => ReturnType<EntryExitAnimationFunction>);

export function useEntering() {
  const reduced = useReducedMotion();

  /**
   * Stagger-capable entry. When reduced-motion is on, returns a quick
   * opacity fade with no translate and no stagger delay.
   */
  const fadeInDown = useCallback(
    (delay = 0, duration = 240): EnteringAnim =>
      reduced
        ? FadeIn.duration(150)
        : FadeInDown.delay(delay).duration(duration),
    [reduced],
  );

  /**
   * Straight fade-in entry with optional delay/duration.
   */
  const fadeIn = useCallback(
    (delay = 0, duration = 200): EnteringAnim =>
      reduced
        ? FadeIn.duration(120)
        : FadeIn.delay(delay).duration(duration),
    [reduced],
  );

  return { reduced, fadeInDown, fadeIn };
}
