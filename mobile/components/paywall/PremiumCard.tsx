/**
 * PremiumCard — premium subscription option within the paywall.
 *
 * Single primary CTA: "Subscribe Now" with #E11D48 on white text
 * meeting WCAG AA contrast (4.70:1). Displays premium benefits.
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

import {
  BG_ELEVATED,
  BORDER_DEFAULT,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRESSED,
} from "../../constants/colors";
import {
  PAYWALL_ANIMATION,
  MIN_TOUCH_TARGET,
} from "../../constants/config";

/** WCAG AA compliant CTA color: #E11D48 on white text = 4.70:1 contrast ratio */
const CTA_SUBSCRIBE = "#E11D48";
const CTA_SUBSCRIBE_PRESSED = "#BE123C";

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
      <View style={styles.container}>
        {/* Header */}
        <View style={styles.header}>
          <Ionicons name="star" size={20} color={CTA_SUBSCRIBE} />
          <Text style={styles.title}>Premium</Text>
        </View>

        {/* Benefits list */}
        <View style={styles.benefits}>
          {PREMIUM_BENEFITS.map((benefit) => (
            <View key={benefit} style={styles.benefitRow}>
              <Ionicons
                name="checkmark-circle"
                size={18}
                color={CTA_SUBSCRIBE}
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
            pressed && !isDisabled && styles.subscribeButtonPressed,
          ]}
          accessibilityLabel={
            isLoading ? "Subscribe Now, loading" : "Subscribe Now"
          }
          accessibilityRole="button"
          accessibilityState={{ disabled: isDisabled, busy: isLoading }}
        >
          {isLoading ? (
            <ActivityIndicator color="#FFFFFF" size="small" />
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
    backgroundColor: BG_ELEVATED,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER_DEFAULT,
    padding: 20,
    gap: 16,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
  },
  title: {
    color: TEXT_PRIMARY,
    fontSize: 20,
    fontWeight: "700",
  },
  benefits: {
    gap: 10,
  },
  benefitRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 10,
  },
  benefitText: {
    color: TEXT_SECONDARY,
    fontSize: 15,
    fontWeight: "500",
  },
  subscribeButton: {
    backgroundColor: CTA_SUBSCRIBE,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
    justifyContent: "center",
    minHeight: MIN_TOUCH_TARGET,
  },
  subscribeButtonPressed: {
    backgroundColor: CTA_SUBSCRIBE_PRESSED,
  },
  subscribeText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "700",
  },
});
