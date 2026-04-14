/**
 * PremiumCard — premium subscription option within the paywall.
 *
 * Glass card with accent border glow. "Subscribe Now" CTA uses the
 * session accent color. Displays premium benefits + plan name and
 * formatted recurring price.
 *
 * Billing interval assumption: backend currently does not expose the
 * Stripe `recurring.interval`, so we hardcode `/mo` (PR1 only ships
 * a monthly Premium price). When backend exposes the interval, replace
 * `BILLING_INTERVAL_SUFFIX` with a value derived from `premium`.
 */
import { useRef, useCallback } from "react";
import {
  Pressable,
  View,
  Animated,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import {
  PAYWALL_ANIMATION,
  MIN_TOUCH_TARGET,
} from "../../constants/config";
import { Body, Caption, Heading } from "../ui/Text";
import { formatPrice } from "../../lib/format-price";
import { PREMIUM_BENEFITS } from "../../constants/premium-benefits";
import type { PremiumOption } from "../../lib/entitlement";

/** Suffix appended to the Premium price (e.g. "/mo"). Monthly-only for now. */
const BILLING_INTERVAL_SUFFIX = "/mo";

interface PremiumCardProps {
  premium: PremiumOption;
  onSubscribe: () => void;
  isLoading: boolean;
  disabled: boolean;
}

export function PremiumCard({
  premium,
  onSubscribe,
  isLoading,
  disabled,
}: PremiumCardProps) {
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

  return (
    <Animated.View
      style={[
        styles.wrapper,
        { transform: [{ scale: scaleAnim }] },
        isDisabled && styles.disabledWrapper,
      ]}
    >
      <View style={[
        styles.container,
        { borderColor: theme.accent + THEME.alpha.med },
        THEME.shadow.glow(theme.accent),
      ]}>
        {/* Header */}
        <View style={styles.header}>
          <Ionicons name="diamond" size={20} color={theme.accent} />
          <Heading size="md">Premium</Heading>
        </View>

        {/* Plan name + price */}
        <Caption weight="medium" style={styles.priceLine}>
          {premium.name} · {formatPrice(premium.amount_cents, premium.currency)}
          {BILLING_INTERVAL_SUFFIX}
        </Caption>

        {/* Benefits list */}
        <View style={styles.benefits}>
          {PREMIUM_BENEFITS.map((benefit) => (
            <View key={benefit} style={styles.benefitRow}>
              <Ionicons
                name="checkmark-circle"
                size={18}
                color={theme.accent}
              />
              <Body weight="medium" color="secondary">
                {benefit}
              </Body>
            </View>
          ))}
        </View>

        {/* CTA */}
        <Pressable
          onPress={onSubscribe}
          onPressIn={handlePressIn}
          onPressOut={handlePressOut}
          disabled={isDisabled}
          style={({ pressed }) => [
            styles.subscribeButton,
            { backgroundColor: theme.accent },
            pressed && !isDisabled && styles.subscribeButtonPressed,
          ]}
          accessibilityLabel={
            isLoading ? "Subscribe Now, loading" : "Subscribe Now"
          }
          accessibilityRole="button"
          accessibilityState={{ disabled: isDisabled, busy: isLoading }}
        >
          {isLoading ? (
            <ActivityIndicator color={THEME.colors.bg} size="small" />
          ) : (
            <Body weight="semibold" color={THEME.colors.bg} style={styles.subscribeText}>
              Subscribe Now
            </Body>
          )}
        </Pressable>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrapper: {},
  disabledWrapper: {
    opacity: 0.5,
  },
  container: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.xl,
    gap: THEME.spacing.lg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
  },
  priceLine: {
    color: THEME.colors.textPrimary,
  },
  benefits: {
    gap: THEME.spacing.md,
  },
  benefitRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
  },
  subscribeButton: {
    borderRadius: THEME.radius.pill,
    paddingVertical: THEME.spacing.lg - 2,
    alignItems: "center",
    justifyContent: "center",
    minHeight: MIN_TOUCH_TARGET,
  },
  subscribeButtonPressed: {
    opacity: 0.85,
  },
  subscribeText: {
    fontSize: 16,
  },
});
