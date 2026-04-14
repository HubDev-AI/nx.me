/**
 * CreditBadge — animated credit count chip.
 *
 * Displays the user's current credit balance using the dynamic session
 * accent color from useTheme(). When the balance changes (e.g. after
 * purchase), the count animates with a scale bounce to draw attention.
 */
import { useEffect, useMemo, useRef } from "react";
import { Text, StyleSheet } from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSequence,
  withTiming,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { PAYWALL_ANIMATION, MIN_TOUCH_TARGET } from "../../constants/config";
import { useTheme } from "../../lib/theme-context";

interface CreditBadgeProps {
  /** Current credit balance to display. */
  balance: number;
  /** Optional size variant. */
  size?: "small" | "default";
}

export function CreditBadge({ balance, size = "default" }: CreditBadgeProps) {
  const { theme } = useTheme();
  const scaleAnim = useSharedValue(1);
  const prevBalance = useRef(balance);

  const accentColors = useMemo(() => ({
    bg: theme.accent + THEME.alpha.subtle,
    border: theme.accent + THEME.alpha.low,
    icon: theme.accent,
    text: theme.accent,
  }), [theme.accent]);

  useEffect(() => {
    if (prevBalance.current !== balance) {
      prevBalance.current = balance;
      scaleAnim.value = withSequence(
        withTiming(PAYWALL_ANIMATION.BOUNCE_SCALE, {
          duration: PAYWALL_ANIMATION.COUNT_ANIMATION_DURATION_MS / 3,
        }),
        withTiming(1, {
          duration: (PAYWALL_ANIMATION.COUNT_ANIMATION_DURATION_MS * 2) / 3,
        }),
      );
    }
  }, [balance, scaleAnim]);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scaleAnim.value }],
  }));

  const isSmall = size === "small";
  const iconSize = isSmall ? 14 : 18;

  return (
    <Animated.View
      style={[
        styles.container,
        isSmall && styles.containerSmall,
        {
          backgroundColor: accentColors.bg,
          borderColor: accentColors.border,
        },
        animatedStyle,
      ]}
      accessibilityLabel={`${balance} credits remaining`}
      accessibilityRole="text"
    >
      <Ionicons name="diamond-outline" size={iconSize} color={accentColors.icon} />
      <Text
        style={[styles.text, { color: accentColors.text }, isSmall && styles.textSmall]}
        accessibilityElementsHidden
      >
        {balance}
      </Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    gap: THEME.spacing.sm,
    borderWidth: 1,
  },
  containerSmall: {
    paddingHorizontal: THEME.spacing.sm,
    paddingVertical: THEME.spacing.xs,
    minHeight: 32,
  },
  text: {
    fontFamily: FONTS.bodyBold,
    ...THEME.typography.body,
    fontVariant: ["tabular-nums"],
  },
  textSmall: {
    ...THEME.typography.caption,
  },
});
