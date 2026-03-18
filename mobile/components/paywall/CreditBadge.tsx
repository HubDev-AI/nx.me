/**
 * CreditBadge — animated credit count chip.
 *
 * Displays the user's current credit balance with an amber-gold accent.
 * When the balance changes (e.g. after purchase), the count animates
 * with a scale bounce to draw attention.
 */
import { useRef, useEffect } from "react";
import { Text, Animated, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  CREDIT_BADGE_BG,
  CREDIT_BADGE_TEXT,
  CREDIT_BADGE_ICON,
} from "../../constants/colors";
import { PAYWALL_ANIMATION, MIN_TOUCH_TARGET } from "../../constants/config";

interface CreditBadgeProps {
  /** Current credit balance to display. */
  balance: number;
  /** Optional size variant. */
  size?: "small" | "default";
}

const BOUNCE_SCALE = 1.15;

export function CreditBadge({ balance, size = "default" }: CreditBadgeProps) {
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const prevBalance = useRef(balance);

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
  const fontSize = isSmall ? 13 : 15;

  return (
    <Animated.View
      style={[
        styles.container,
        isSmall && styles.containerSmall,
        { transform: [{ scale: scaleAnim }] },
      ]}
      accessibilityLabel={`${balance} credits remaining`}
      accessibilityRole="text"
    >
      <Ionicons name="diamond-outline" size={iconSize} color={CREDIT_BADGE_ICON} />
      <Text
        style={[styles.text, { fontSize }]}
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
    backgroundColor: CREDIT_BADGE_BG,
    borderRadius: 20,
    paddingHorizontal: 12,
    paddingVertical: 6,
    minHeight: MIN_TOUCH_TARGET,
    gap: 6,
  },
  containerSmall: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    minHeight: 32,
  },
  text: {
    color: CREDIT_BADGE_TEXT,
    fontWeight: "700",
  },
});
