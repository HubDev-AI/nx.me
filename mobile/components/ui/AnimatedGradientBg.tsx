/**
 * SoftGlowBg — warm, dreamy bokeh-style background for a beauty app.
 * Soft blush/rose/champagne light spots that breathe gently.
 * Think: luxury beauty counter lighting, not sci-fi aurora.
 */
import { useEffect } from "react";
import { StyleSheet, Dimensions } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSequence,
  withDelay,
  Easing,
} from "react-native-reanimated";

const { width: SCREEN_W, height: SCREEN_H } = Dimensions.get("window");

interface AnimatedGradientBgProps {
  /** Warm highlight — blush/rose */
  color1?: string;
  /** Soft accent — champagne/peach */
  color2?: string;
  /** Deep tone — mauve/plum */
  color3?: string;
  /** Overall opacity */
  opacity?: number;
  /** Cycle duration in ms (slower = more luxurious) */
  duration?: number;
}

export function AnimatedGradientBg({
  color1 = "rgba(244, 143, 177, 0.18)",
  color2 = "rgba(255, 213, 179, 0.14)",
  color3 = "rgba(206, 147, 216, 0.12)",
  opacity = 1,
  duration = 12000,
}: AnimatedGradientBgProps) {
  const p1 = useSharedValue(0);
  const p2 = useSharedValue(0);
  const p3 = useSharedValue(0);
  const p4 = useSharedValue(0);

  useEffect(() => {
    // Soft, slow breathing — beauty lighting rhythm
    p1.value = withRepeat(
      withSequence(
        withTiming(1, { duration, easing: Easing.inOut(Easing.sin) }),
        withTiming(0, { duration, easing: Easing.inOut(Easing.sin) }),
      ),
      -1, false,
    );

    p2.value = withDelay(duration * 0.25,
      withRepeat(
        withSequence(
          withTiming(1, { duration: duration * 1.3, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: duration * 1.3, easing: Easing.inOut(Easing.sin) }),
        ),
        -1, false,
      ),
    );

    p3.value = withDelay(duration * 0.5,
      withRepeat(
        withSequence(
          withTiming(1, { duration: duration * 0.85, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: duration * 0.85, easing: Easing.inOut(Easing.sin) }),
        ),
        -1, false,
      ),
    );

    // Tiny warm sparkle dot
    p4.value = withDelay(duration * 0.7,
      withRepeat(
        withSequence(
          withTiming(1, { duration: duration * 0.6, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: duration * 0.6, easing: Easing.inOut(Easing.sin) }),
        ),
        -1, false,
      ),
    );
  }, [duration, p1, p2, p3, p4]);

  // Large soft blush glow — top area
  const glow1 = useAnimatedStyle(() => ({
    opacity: 0.4 + p1.value * 0.6,
    transform: [
      { translateY: p1.value * 30 - 15 },
      { scale: 1 + p1.value * 0.08 },
    ],
  }));

  // Warm champagne glow — mid-right
  const glow2 = useAnimatedStyle(() => ({
    opacity: 0.3 + p2.value * 0.5,
    transform: [
      { translateX: p2.value * 20 - 10 },
      { translateY: p2.value * -15 + 7 },
      { scale: 1 + p2.value * 0.1 },
    ],
  }));

  // Deep mauve — bottom-left
  const glow3 = useAnimatedStyle(() => ({
    opacity: 0.35 + p3.value * 0.45,
    transform: [
      { translateX: p3.value * -15 + 7 },
      { translateY: p3.value * 20 - 10 },
      { scale: 1.05 - p3.value * 0.05 },
    ],
  }));

  // Tiny warm sparkle highlight
  const sparkle = useAnimatedStyle(() => ({
    opacity: p4.value * 0.5,
    transform: [{ scale: 0.8 + p4.value * 0.4 }],
  }));

  return (
    <Animated.View style={[styles.container, { opacity }]} pointerEvents="none">
      {/* Large blush glow — top */}
      <Animated.View
        style={[
          styles.glow,
          {
            width: SCREEN_W * 1.4,
            height: SCREEN_W * 1.4,
            borderRadius: SCREEN_W * 0.7,
            backgroundColor: color1,
            top: -SCREEN_W * 0.5,
            left: -SCREEN_W * 0.2,
          },
          glow1,
        ]}
      />
      {/* Champagne glow — right */}
      <Animated.View
        style={[
          styles.glow,
          {
            width: SCREEN_W * 0.9,
            height: SCREEN_W * 0.9,
            borderRadius: SCREEN_W * 0.45,
            backgroundColor: color2,
            top: SCREEN_H * 0.25,
            right: -SCREEN_W * 0.25,
          },
          glow2,
        ]}
      />
      {/* Mauve glow — bottom-left */}
      <Animated.View
        style={[
          styles.glow,
          {
            width: SCREEN_W * 1.0,
            height: SCREEN_W * 1.0,
            borderRadius: SCREEN_W * 0.5,
            backgroundColor: color3,
            bottom: -SCREEN_W * 0.2,
            left: -SCREEN_W * 0.15,
          },
          glow3,
        ]}
      />
      {/* Warm sparkle dot */}
      <Animated.View
        style={[
          styles.glow,
          {
            width: 80,
            height: 80,
            borderRadius: 40,
            backgroundColor: "rgba(255, 236, 210, 0.25)",
            top: SCREEN_H * 0.15,
            right: SCREEN_W * 0.15,
          },
          sparkle,
        ]}
      />
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    ...StyleSheet.absoluteFillObject,
    overflow: "hidden",
  },
  glow: {
    position: "absolute",
  },
});
