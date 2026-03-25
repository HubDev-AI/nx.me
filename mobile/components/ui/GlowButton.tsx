/**
 * GlowButton — CTA button with pulsing glow shadow effect.
 * The glow pulses subtly to draw attention without being distracting.
 */
import { useEffect, useCallback } from "react";
import {
  Text,
  Pressable,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withSequence,
  withTiming,
  withSpring,
  withDelay,
  Easing,
} from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import { hapticLight } from "../../lib/haptics";
import { FONTS } from "../../hooks/useFonts";

interface GlowButtonProps {
  title: string;
  onPress: () => void;
  isLoading?: boolean;
  disabled?: boolean;
  /** Glow color — defaults to CTA coral */
  glowColor?: string;
  /** Size variant */
  size?: "default" | "large";
}

export function GlowButton({
  title,
  onPress,
  isLoading = false,
  disabled = false,
  glowColor = THEME.colors.textPrimary,
  size = "default",
}: GlowButtonProps) {
  const glowPulse = useSharedValue(0);
  const pressScale = useSharedValue(1);
  const textScale = useSharedValue(0.85);

  const isDisabled = disabled || isLoading;

  useEffect(() => {
    if (!isDisabled) {
      glowPulse.value = withRepeat(
        withSequence(
          withTiming(1, { duration: 2000, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: 2000, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
        false,
      );
      // Subtle scale spring on text when button appears
      textScale.value = withDelay(
        200,
        withSpring(1, { damping: 12, stiffness: 180 }),
      );
    } else {
      glowPulse.value = withTiming(0, { duration: 300 });
      textScale.value = 1;
    }
  }, [isDisabled, glowPulse, textScale]);

  const handlePress = useCallback(() => {
    hapticLight();
    onPress();
  }, [onPress]);

  const handlePressIn = useCallback(() => {
    pressScale.value = withSpring(0.96, THEME.animation.press);
  }, [pressScale]);

  const handlePressOut = useCallback(() => {
    pressScale.value = withSpring(1, THEME.animation.press);
  }, [pressScale]);

  const glowStyle = useAnimatedStyle(() => ({
    shadowOpacity: 0.3 + glowPulse.value * 0.5,
    shadowRadius: 12 + glowPulse.value * 16,
    transform: [{ scale: pressScale.value }],
  }));

  const innerGlowStyle = useAnimatedStyle(() => ({
    opacity: 0.08 + glowPulse.value * 0.12,
  }));

  const textSpringStyle = useAnimatedStyle(() => ({
    transform: [{ scale: textScale.value }],
  }));

  return (
    <Animated.View
      style={[
        styles.wrapper,
        {
          shadowColor: glowColor,
          shadowOffset: { width: 0, height: 4 },
        },
        isDisabled && styles.disabledWrapper,
        glowStyle,
      ]}
    >
      <Pressable
        onPress={handlePress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isDisabled}
        style={[
          styles.button,
          { backgroundColor: glowColor },
          size === "large" && styles.buttonLarge,
        ]}
        accessibilityLabel={isLoading ? `${title}, loading` : title}
        accessibilityRole="button"
        accessibilityState={{ disabled: isDisabled, busy: isLoading }}
      >
        {/* Inner glow overlay */}
        <Animated.View
          style={[
            styles.innerGlow,
            { backgroundColor: THEME.colors.white },
            innerGlowStyle,
          ]}
          pointerEvents="none"
        />

        {isLoading ? (
          <ActivityIndicator color={THEME.colors.white} size="small" />
        ) : (
          <Animated.View style={textSpringStyle}>
            <Text style={[styles.text, size === "large" && styles.textLarge]}>
              {title}
            </Text>
          </Animated.View>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    borderRadius: THEME.radius.pill,
    shadowOffset: { width: 0, height: 4 },
    elevation: 8,
  },
  disabledWrapper: {
    opacity: 0.5,
    shadowOpacity: 0,
  },
  button: {
    backgroundColor: THEME.colors.textPrimary,
    minHeight: 48,
    borderRadius: THEME.radius.pill,
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 13,
    paddingHorizontal: 24,
    overflow: "hidden",
  },
  buttonLarge: {
    minHeight: 56,
    paddingVertical: 16,
    borderRadius: THEME.radius.pill,
  },
  innerGlow: {
    ...StyleSheet.absoluteFillObject,
    borderRadius: THEME.radius.pill,
  },
  text: {
    fontFamily: FONTS.bodyMedium,
    color: THEME.colors.bg,
    fontSize: 16,
    letterSpacing: 0.3,
  },
  textLarge: {
    fontSize: 18,
    letterSpacing: 0.5,
  },
});
