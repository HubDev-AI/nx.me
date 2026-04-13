/**
 * Unified Button — single API for every CTA in the app. Supports pulsing
 * glow, haptics, leading/trailing icons, loading state, and five variants
 * (primary / secondary / destructive / outline / ghost). Prefer this over
 * raw Pressable for any tappable call-to-action.
 *
 * Variants:
 *   primary     — filled with session accent (optionally glowing)
 *   secondary   — elevated surface with subtle border
 *   destructive — red filled (use for delete/logout)
 *   outline     — transparent with border (secondary actions)
 *   ghost       — text-only (tertiary actions)
 *
 * Sizes: sm (40), md (48, default), lg (56) — all meet iOS HIG 44pt minimum.
 */
import type { ReactNode } from "react";
import { useCallback, useEffect, useMemo } from "react";
import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text as RNText,
  type StyleProp,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import Animated, {
  Easing,
  useAnimatedStyle,
  useSharedValue,
  withRepeat,
  withSequence,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { hapticError, hapticLight, hapticMedium } from "../../lib/haptics";
import { useTheme } from "../../lib/theme-context";

export type ButtonVariant = "primary" | "secondary" | "destructive" | "outline" | "ghost";
export type ButtonSize = "sm" | "md" | "lg";
type HapticStrength = "none" | "light" | "medium" | "error";

interface SizeToken {
  minHeight: number;
  paddingH: number;
  paddingV: number;
  fontSize: number;
}

const SIZE: Record<ButtonSize, SizeToken> = {
  sm: { minHeight: 40, paddingH: THEME.spacing.lg, paddingV: THEME.spacing.sm, fontSize: 14 },
  md: { minHeight: 48, paddingH: THEME.spacing.xxl, paddingV: THEME.spacing.md, fontSize: 16 },
  lg: { minHeight: 56, paddingH: THEME.spacing.xxl, paddingV: THEME.spacing.lg, fontSize: 18 },
};

interface ButtonProps {
  title: string;
  onPress: () => void;
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
  disabled?: boolean;
  /** Enable pulsing-glow shadow (typically for hero CTAs). */
  glow?: boolean;
  /** Override glow shadow color (defaults to accent / variant fill). */
  glowColor?: string;
  /** Override accent fill for primary variant (defaults to session accent). */
  accentColor?: string;
  haptic?: HapticStrength;
  leftIcon?: ReactNode;
  rightIcon?: ReactNode;
  /** Occupy full width of parent. */
  block?: boolean;
  style?: StyleProp<ViewStyle>;
  textStyle?: StyleProp<TextStyle>;
  accessibilityLabel?: string;
  testID?: string;
}

export function Button({
  title,
  onPress,
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled = false,
  glow = false,
  glowColor,
  accentColor,
  haptic = "light",
  leftIcon,
  rightIcon,
  block = false,
  style,
  textStyle,
  accessibilityLabel,
  testID,
}: ButtonProps) {
  const { theme } = useTheme();
  const fillColor = accentColor ?? theme.accent;
  const resolvedGlow = glowColor ?? fillColor;
  const isDisabled = disabled || isLoading;

  const glowPulse = useSharedValue(0);
  const pressScale = useSharedValue(1);

  useEffect(() => {
    if (glow && !isDisabled) {
      glowPulse.value = withRepeat(
        withSequence(
          withTiming(1, { duration: 2000, easing: Easing.inOut(Easing.sin) }),
          withTiming(0, { duration: 2000, easing: Easing.inOut(Easing.sin) }),
        ),
        -1,
        false,
      );
    } else {
      glowPulse.value = withTiming(0, { duration: THEME.animation.duration.normal });
    }
  }, [glow, isDisabled, glowPulse]);

  const fireHaptic = useCallback(() => {
    if (haptic === "none") return;
    if (haptic === "medium") return hapticMedium();
    if (haptic === "error") return hapticError();
    return hapticLight();
  }, [haptic]);

  const handlePress = useCallback(() => {
    fireHaptic();
    onPress();
  }, [onPress, fireHaptic]);

  const handlePressIn = useCallback(() => {
    pressScale.value = withSpring(0.96, THEME.animation.press);
  }, [pressScale]);

  const handlePressOut = useCallback(() => {
    pressScale.value = withSpring(1, THEME.animation.press);
  }, [pressScale]);

  const wrapperStyle = useAnimatedStyle(() => ({
    transform: [{ scale: pressScale.value }],
    shadowOpacity: glow ? 0.3 + glowPulse.value * 0.5 : 0,
    shadowRadius: glow ? 12 + glowPulse.value * 16 : 0,
  }));

  const sz = SIZE[size];

  const variantStyle = useMemo<{
    bg: string;
    borderColor: string;
    borderWidth: number;
    textColor: string;
  }>(() => {
    switch (variant) {
      case "primary":
        return { bg: fillColor, borderColor: "transparent", borderWidth: 0, textColor: THEME.colors.bg };
      case "destructive":
        return { bg: THEME.colors.destructive, borderColor: "transparent", borderWidth: 0, textColor: THEME.colors.white };
      case "secondary":
        return {
          bg: THEME.colors.surfaceElevated,
          borderColor: THEME.colors.border,
          borderWidth: 1,
          textColor: THEME.colors.textPrimary,
        };
      case "outline":
        return {
          bg: "transparent",
          borderColor: THEME.colors.borderFocused,
          borderWidth: 1,
          textColor: THEME.colors.textPrimary,
        };
      case "ghost":
        return { bg: "transparent", borderColor: "transparent", borderWidth: 0, textColor: fillColor };
    }
  }, [variant, fillColor]);

  return (
    <Animated.View
      style={[
        styles.wrapper,
        block && styles.block,
        glow && {
          shadowColor: resolvedGlow,
          shadowOffset: { width: 0, height: 4 },
          elevation: 8,
        },
        isDisabled && styles.disabled,
        wrapperStyle,
        style,
      ]}
    >
      <Pressable
        onPress={handlePress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isDisabled}
        hitSlop={8}
        style={[
          styles.button,
          {
            backgroundColor: variantStyle.bg,
            borderColor: variantStyle.borderColor,
            borderWidth: variantStyle.borderWidth,
            minHeight: sz.minHeight,
            paddingHorizontal: sz.paddingH,
            paddingVertical: sz.paddingV,
          },
        ]}
        accessibilityLabel={accessibilityLabel ?? (isLoading ? `${title}, loading` : title)}
        accessibilityRole="button"
        accessibilityState={{ disabled: isDisabled, busy: isLoading }}
        testID={testID}
      >
        {isLoading ? (
          <ActivityIndicator color={variantStyle.textColor} size="small" />
        ) : (
          <>
            {leftIcon}
            <RNText
              numberOfLines={1}
              style={[
                styles.text,
                { color: variantStyle.textColor, fontSize: sz.fontSize },
                textStyle,
              ]}
            >
              {title}
            </RNText>
            {rightIcon}
          </>
        )}
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    borderRadius: THEME.radius.pill,
    alignSelf: "flex-start",
  },
  block: {
    alignSelf: "stretch",
  },
  disabled: {
    opacity: 0.5,
  },
  button: {
    borderRadius: THEME.radius.pill,
    borderCurve: "continuous",
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: THEME.spacing.sm,
    overflow: "hidden",
  },
  text: {
    fontFamily: FONTS.bodyMedium,
    letterSpacing: 0.3,
  },
});
