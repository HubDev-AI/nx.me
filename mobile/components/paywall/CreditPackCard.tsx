/**
 * CreditPackCard — selectable credit pack option within the paywall.
 *
 * Displays credit count and a "Buy" CTA. Press feedback follows the
 * NXME pattern: scale 0.98 over 150ms, min 44pt touch target.
 */
import { useRef, useCallback } from "react";
import { Pressable, Text, View, Animated, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_CARD,
  BORDER_DEFAULT,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  CTA_PRESSED,
  CREDIT_BADGE_ICON,
} from "../../constants/colors";
import {
  PAYWALL_ANIMATION,
  MIN_TOUCH_TARGET,
} from "../../constants/config";
import type { CreditPackOption } from "../../lib/entitlement";

interface CreditPackCardProps {
  pack: CreditPackOption;
  onPurchase: (pack: CreditPackOption) => void;
  isLoading: boolean;
  disabled: boolean;
}

export function CreditPackCard({
  pack,
  onPurchase,
  isLoading,
  disabled,
}: CreditPackCardProps) {
  const scaleAnim = useRef(new Animated.Value(1)).current;
  const isDisabled = disabled || isLoading;

  const handlePressIn = useCallback(() => {
    Animated.timing(scaleAnim, {
      toValue: PAYWALL_ANIMATION.PRESS_SCALE,
      duration: PAYWALL_ANIMATION.PRESS_DURATION_MS,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const handlePressOut = useCallback(() => {
    Animated.timing(scaleAnim, {
      toValue: 1,
      duration: PAYWALL_ANIMATION.PRESS_DURATION_MS,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const handlePress = useCallback(() => {
    onPurchase(pack);
  }, [onPurchase, pack]);

  /** Derive a display label from the pack_id (e.g. "10_credits" -> "10 Credits") */
  const displayCredits = pack.credits;
  const displayLabel = `${displayCredits} Credits`;

  return (
    <Animated.View
      style={[
        styles.wrapper,
        { transform: [{ scale: scaleAnim }] },
        isDisabled && styles.disabledWrapper,
      ]}
    >
      <Pressable
        onPress={handlePress}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={isDisabled}
        style={styles.container}
        accessibilityLabel={`Purchase ${displayLabel}`}
        accessibilityRole="button"
        accessibilityState={{ disabled: isDisabled, busy: isLoading }}
      >
        <View style={styles.left}>
          <Ionicons
            name="diamond-outline"
            size={24}
            color={CREDIT_BADGE_ICON}
          />
          <Text style={styles.creditCount}>{displayCredits}</Text>
          <Text style={styles.label}>credits</Text>
        </View>

        <View
          style={[
            styles.buyButton,
            isDisabled && styles.buyButtonDisabled,
          ]}
        >
          <Text style={styles.buyText}>Buy</Text>
        </View>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {},
  disabledWrapper: {
    opacity: 0.5,
  },
  container: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    backgroundColor: BG_CARD,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: BORDER_DEFAULT,
    paddingHorizontal: 16,
    paddingVertical: 14,
    minHeight: MIN_TOUCH_TARGET,
  },
  left: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  creditCount: {
    color: TEXT_PRIMARY,
    fontSize: 18,
    fontWeight: "700",
  },
  label: {
    color: TEXT_SECONDARY,
    fontSize: 14,
    fontWeight: "500",
  },
  buyButton: {
    backgroundColor: CTA_PRIMARY,
    borderRadius: 8,
    paddingHorizontal: 20,
    paddingVertical: 8,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
    alignItems: "center",
  },
  buyButtonDisabled: {
    backgroundColor: CTA_PRESSED,
  },
  buyText: {
    color: "#FFFFFF",
    fontSize: 14,
    fontWeight: "700",
  },
});
