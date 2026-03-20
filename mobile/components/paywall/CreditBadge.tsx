/**
 * CreditBadge — animated credit count chip.
 *
 * Displays the user's current credit balance using the dynamic session
 * accent color from useTheme(). When the balance changes (e.g. after
 * purchase), the count animates with a scale bounce to draw attention.
 */
import { useRef, useEffect, useMemo } from "react";
import { Text, Animated, StyleSheet } from "react-native";
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

const BOUNCE_SCALE = 1.15;

export function CreditBadge({ balance, size = "default" }: CreditBadgeProps) {
  const { theme } = useTheme();
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const prevBalance = useRef(balance);

  // Derive accent-based colors
  const accentColors = useMemo(() => ({
    bg: theme.accent + "26", // ~15% opacity
    border: theme.accent + "33", // ~20% opacity
    icon: theme.accent,
    text: theme.accent,
  }), [theme.accent]);

  // Animate bounce when balance changes
  useEffect(() => {
    if (prevBalance.current !== balance) {
      prevBalance.current = balance;

      Animated.sequence([
        Animated.timing(scaleAnim, {
          toValue: BOUNCE_SCALE,
          duration: PAYWALL_ANIMATION.COUNT_ANIMATION_DURATION_MS / 3,
          useNativeDriver: true,
        }),
        Animated.timing(scaleAnim, {
          toValue: 1,
          duration: (PAYWALL_ANIMATION.COUNT_ANIMATION_DURATION_MS * 2) / 3,
          useNativeDriver: true,
        }),
      ]).start();
    }
  }, [balance, scaleAnim]);

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
          transform: [{ scale: scaleAnim }],
        },
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
  },
  textSmall: {
    ...THEME.typography.caption,
  },
});
