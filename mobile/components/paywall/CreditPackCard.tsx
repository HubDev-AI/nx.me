/**
 * CreditPackCard — selectable credit pack option within the paywall.
 *
 * Displays credit count, formatted price and a "Buy" CTA. Press feedback
 * follows the NXME pattern: scale 0.98 over 150ms, min 44pt touch target.
 */
import { useRef, useCallback } from "react";
import { Pressable, Text, View, Animated, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import {
  PAYWALL_ANIMATION,
  MIN_TOUCH_TARGET,
} from "../../constants/config";
import { Body, Caption } from "../ui/Text";
import { formatPrice } from "../../lib/format-price";
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
  const { theme } = useTheme();
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

  const formattedPrice = formatPrice(pack.amount_cents, pack.currency);

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
        accessibilityLabel={`Purchase ${pack.credits} credits for ${formattedPrice}`}
        accessibilityRole="button"
        accessibilityState={{ disabled: isDisabled, busy: isLoading }}
      >
        <View style={styles.left}>
          <Ionicons
            name="diamond-outline"
            size={24}
            color={THEME.colors.creditAccent}
          />
          {/* Numeric count — keeps tabular-nums + custom bold face. */}
          <Text style={styles.creditCount}>{pack.credits}</Text>
          <Caption weight="medium">credits</Caption>
          <Caption style={styles.priceSeparator}>·</Caption>
          <Caption weight="medium" style={styles.price}>
            {formattedPrice}
          </Caption>
        </View>

        <View
          style={[
            styles.buyButton,
            { backgroundColor: theme.accent },
            isDisabled && styles.buyButtonDisabled,
          ]}
        >
          <Body weight="bold" color={THEME.colors.bg} style={styles.buyText}>
            Buy
          </Body>
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
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingHorizontal: THEME.spacing.lg,
    paddingVertical: THEME.spacing.lg - 2,
    minHeight: MIN_TOUCH_TARGET,
  },
  left: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
  },
  creditCount: {
    fontFamily: FONTS.bodyBold,
    color: THEME.colors.textPrimary,
    fontSize: 18,
  },
  priceSeparator: {
    color: THEME.colors.textMuted,
  },
  price: {
    color: THEME.colors.textPrimary,
  },
  buyButton: {
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
    alignItems: "center",
  },
  buyButtonDisabled: {
    opacity: 0.6,
  },
  buyText: {
    fontSize: 14,
  },
});
