/**
 * PremiumCard — premium subscription option within the paywall.
 *
 * Glass card with accent border glow. "Subscribe Now" CTA uses the
 * session accent color. Displays premium benefits list.
 */
import { useRef, useCallback } from "react";
import {
  Pressable,
  Text,
  View,
  Animated,
  ActivityIndicator,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";
import {
  PAYWALL_ANIMATION,
  MIN_TOUCH_TARGET,
} from "../../constants/config";

const PREMIUM_BENEFITS = [
  "Unlimited generations",
  "Priority processing",
  "Advanced style options",
] as const;

interface PremiumCardProps {
  onSubscribe: () => void;
  isLoading: boolean;
  disabled: boolean;
}

export function PremiumCard({
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
          <Ionicons name="star" size={20} color={theme.accent} />
          <Text style={styles.title}>Premium</Text>
        </View>

        {/* Benefits list */}
        <View style={styles.benefits}>
          {PREMIUM_BENEFITS.map((benefit) => (
            <View key={benefit} style={styles.benefitRow}>
              <Ionicons
                name="checkmark-circle"
                size={18}
                color={theme.accent}
              />
              <Text style={styles.benefitText}>{benefit}</Text>
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
            <Text style={styles.subscribeText}>Subscribe Now</Text>
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
  title: {
    fontFamily: FONTS.display,
    color: THEME.colors.textPrimary,
    fontSize: 20,
  },
  benefits: {
    gap: THEME.spacing.md,
  },
  benefitRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
  },
  benefitText: {
    fontFamily: FONTS.bodyMedium,
    color: THEME.colors.textSecondary,
    ...THEME.typography.body,
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
    fontFamily: FONTS.bodySemiBold,
    color: THEME.colors.bg,
    fontSize: 16,
  },
});
