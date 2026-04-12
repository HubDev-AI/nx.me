/**
 * ShimmerLogo — NXME wordmark with animated shimmer sweep + subtle glow.
 * Creates a futuristic, premium feel on auth screens.
 */
import { useEffect } from "react";
import { StyleSheet, View } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withDelay,
  Easing,
  interpolate,
} from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";

interface ShimmerLogoProps {
  /** Font size */
  size?: number;
  /** Glow color — defaults to CTA coral */
  glowColor?: string;
}

export function ShimmerLogo({ size = 36, glowColor = THEME.colors.textPrimary }: ShimmerLogoProps) {
  const shimmer = useSharedValue(0);
  const glow = useSharedValue(0);

  useEffect(() => {
    // One-shot shimmer sweep on mount — animations users see on every auth
    // visit become visual noise. The subtle glow pulse still loops.
    shimmer.value = withDelay(
      400,
      withTiming(1, {
        duration: 1200,
        easing: Easing.bezier(0.77, 0, 0.175, 1),
      }),
    );

    // Gentle glow pulse
    glow.value = withRepeat(
      withTiming(1, { duration: 3000, easing: Easing.inOut(Easing.sin) }),
      -1,
      true,
    );
  }, [glow, shimmer]);

  const textStyle = useAnimatedStyle(() => ({
    opacity: interpolate(glow.value, [0, 1], [0.85, 1]),
    textShadowRadius: interpolate(glow.value, [0, 1], [8, 20]),
    textShadowColor: glowColor,
  }));

  const shimmerOverlayStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: interpolate(shimmer.value, [0, 1], [-200, 300]) },
    ],
    opacity: interpolate(shimmer.value, [0, 0.3, 0.7, 1], [0, 0.6, 0.6, 0]),
  }));

  return (
    <View style={styles.container}>
      <Animated.Text
        style={[
          styles.logo,
          {
            fontSize: size,
            textShadowOffset: { width: 0, height: 0 },
          },
          textStyle,
        ]}
        accessibilityRole="header"
      >
        NXME
      </Animated.Text>

      {/* Shimmer sweep overlay */}
      <Animated.View
        style={[styles.shimmerOverlay, shimmerOverlayStyle]}
        pointerEvents="none"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: "center",
    overflow: "hidden",
    paddingVertical: 8,
  },
  logo: {
    fontFamily: FONTS.displayItalic,
    color: THEME.colors.textPrimary,
    letterSpacing: 8,
  },
  shimmerOverlay: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: 60,
    backgroundColor: "rgba(255, 255, 255, 0.15)",
    transform: [{ skewX: "-20deg" }],
  },
});
