/**
 * PaywallModal — full paywall sheet triggered when blocked_reason is set.
 *
 * Shows a CTA driven by `getPaywallCta()` (pure function), plus pack and
 * Pro options from `purchase_options`. Modal UX: scale+fade entry from
 * trigger, swipe-down dismiss, ~50% scrim.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AccessibilityInfo,
  ActivityIndicator,
  Modal,
  PanResponder,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import Animated, {
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { SUCCESS_DARK } from "../../constants/colors";
import { PAYWALL_ANIMATION, MIN_TOUCH_TARGET } from "../../constants/config";
import { Body, Caption, Heading, Label } from "../ui/Text";
import type { EntitlementState } from "../../lib/entitlement";
import {
  PURCHASING_PREMIUM_ID,
  usePurchaseFlow,
} from "../../lib/hooks/use-purchase-flow";
import { getPaywallCta } from "../../lib/paywall-cta";
import { CreditBadge } from "./CreditBadge";
import { PremiumCard } from "./PremiumCard";

interface PaywallModalProps {
  visible: boolean;
  onClose: () => void;
  /** Called after a successful purchase with updated entitlement state. */
  onPurchaseComplete?: (state: EntitlementState) => void;
  /** When set, the modal heading and preview adapt for the named locked feature. */
  action?: "makeup";
}

/** Sheet position offsets for entry/exit animations. */
const SHEET_OFFSCREEN_OFFSET = 60;
const SHEET_INITIAL_SCALE = 0.95;

/**
 * Spring config used when the swipe-to-dismiss gesture is released below the
 * dismiss threshold and the sheet snaps back to `panY: 0`.
 */
const PAN_RELEASE_SPRING = { damping: 20, stiffness: 150 } as const;

export function PaywallModal({
  visible,
  onClose,
  onPurchaseComplete,
  action,
}: PaywallModalProps) {
  const [showSuccess, setShowSuccess] = useState(false);

  const {
    entitlement,
    isLoading: isFetching,
    error: fetchError,
    purchasingId,
    refresh,
    subscribe,
  } = usePurchaseFlow({
    autoLoad: false,
    onPurchaseComplete: (state) => {
      setShowSuccess(true);
      onPurchaseComplete?.(state);
    },
  });

  const isPurchasing = purchasingId !== null;

  const closeButtonRef = useRef<React.ElementRef<typeof Pressable>>(null);

  // ---------------------------------------------------------------------------
  // Animation shared values
  // ---------------------------------------------------------------------------
  const backdropOpacity = useSharedValue(0);
  const sheetTranslateY = useSharedValue(SHEET_OFFSCREEN_OFFSET);
  const sheetScale = useSharedValue(SHEET_INITIAL_SCALE);
  const panY = useSharedValue(0);

  const backdropStyle = useAnimatedStyle(() => ({
    opacity: backdropOpacity.value,
  }));

  const sheetStyle = useAnimatedStyle(() => ({
    transform: [
      { translateY: sheetTranslateY.value + panY.value },
      { scale: sheetScale.value },
    ],
  }));

  const animateIn = useCallback(() => {
    sheetTranslateY.value = SHEET_OFFSCREEN_OFFSET;
    sheetScale.value = SHEET_INITIAL_SCALE;
    backdropOpacity.value = 0;
    panY.value = 0;

    backdropOpacity.value = withTiming(PAYWALL_ANIMATION.SCRIM_OPACITY, {
      duration: PAYWALL_ANIMATION.ENTER_DURATION_MS,
    });
    sheetTranslateY.value = withTiming(0, {
      duration: PAYWALL_ANIMATION.ENTER_DURATION_MS,
    });
    sheetScale.value = withTiming(1, {
      duration: PAYWALL_ANIMATION.ENTER_DURATION_MS,
    });
  }, [backdropOpacity, sheetTranslateY, sheetScale, panY]);

  const animateOut = useCallback(
    (callback: () => void) => {
      backdropOpacity.value = withTiming(0, {
        duration: PAYWALL_ANIMATION.EXIT_DURATION_MS,
      });
      sheetScale.value = withTiming(SHEET_INITIAL_SCALE, {
        duration: PAYWALL_ANIMATION.EXIT_DURATION_MS,
      });
      sheetTranslateY.value = withTiming(
        SHEET_OFFSCREEN_OFFSET,
        { duration: PAYWALL_ANIMATION.EXIT_DURATION_MS },
        (finished) => {
          if (finished) runOnJS(callback)();
        },
      );
    },
    [backdropOpacity, sheetTranslateY, sheetScale],
  );

  const handleClose = useCallback(() => {
    if (isPurchasing) return;
    animateOut(() => {
      setShowSuccess(false);
      onClose();
    });
  }, [isPurchasing, animateOut, onClose]);

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => false,
        onMoveShouldSetPanResponder: (_, gestureState) =>
          gestureState.dy > PAYWALL_ANIMATION.PAN_MOVE_THRESHOLD,
        onPanResponderMove: (_, gestureState) => {
          if (gestureState.dy > 0) {
            panY.value = gestureState.dy;
          }
        },
        onPanResponderRelease: (_, gestureState) => {
          if (gestureState.dy > PAYWALL_ANIMATION.SWIPE_DISMISS_THRESHOLD) {
            handleClose();
          } else {
            panY.value = withSpring(0, PAN_RELEASE_SPRING);
          }
        },
      }),
    [panY, handleClose],
  );

  useEffect(() => {
    if (visible) {
      animateIn();
      refresh();
      AccessibilityInfo.announceForAccessibility("Dialog opened");
      closeButtonRef.current?.focus();
    }
  }, [visible, animateIn, refresh]);

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------
  const remainingGlowups = entitlement?.remaining_glowups ?? 0;
  const purchaseOptions = entitlement?.purchase_options;
  const proOption = purchaseOptions?.pro ?? null;

  const cta =
    entitlement != null
      ? getPaywallCta(
          entitlement.tier,
          entitlement.subscription_status,
          entitlement.blocked_reason,
        )
      : null;

  const showProCard =
    !isFetching &&
    !fetchError &&
    proOption != null &&
    cta != null &&
    (cta.type === "subscribe" || cta.type === "update_card");

  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleClose}
      statusBarTranslucent
    >
      {/* Scrim backdrop */}
      <Animated.View style={[styles.backdrop, backdropStyle]}>
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={handleClose}
          accessibilityLabel="Close paywall"
          accessibilityRole="button"
        />
      </Animated.View>

      {/* Sheet */}
      <Animated.View
        style={[styles.sheet, sheetStyle]}
        {...panResponder.panHandlers}
      >
        {/* Drag handle */}
        <View style={styles.handleBar} />

        {/* Header */}
        <View style={styles.header}>
          <Heading size="md">
            {action === "makeup" ? "Unlock AI Makeup" : "Get More Glow-Ups"}
          </Heading>
          <Pressable
            ref={closeButtonRef}
            onPress={handleClose}
            hitSlop={12}
            accessibilityLabel="Close"
            accessibilityRole="button"
            style={styles.closeButton}
          >
            <Ionicons name="close" size={24} color={THEME.colors.textSecondary} />
          </Pressable>
        </View>

        {/* Credit badge */}
        <View style={styles.badgeRow}>
          <CreditBadge balance={remainingGlowups} />
          {entitlement && (
            <Caption color="secondary">
              {entitlement.blocked_reason === "none"
                ? "You can generate"
                : "No credits remaining"}
            </Caption>
          )}
        </View>

        {/* CTA label when loaded */}
        {cta != null &&
          cta.type !== "no_paywall" &&
          cta.type !== "wait_for_refill" && (
            <View style={styles.ctaRow}>
              <Label>{cta.primary.label}</Label>
            </View>
          )}

        {/* Content */}
        <ScrollView
          style={styles.scrollContent}
          contentContainerStyle={styles.scrollContentContainer}
          showsVerticalScrollIndicator={false}
          bounces={false}
        >
          {/* Loading state */}
          {isFetching && (
            <View style={styles.centerState}>
              <ActivityIndicator color={THEME.colors.textSecondary} size="large" />
              <Body color="secondary" style={styles.centerStateText}>
                Loading pricing...
              </Body>
            </View>
          )}

          {/* Error state */}
          {fetchError && !isFetching && (
            <View style={styles.centerState}>
              <Ionicons name="alert-circle" size={32} color={THEME.colors.destructive} />
              <Body color="destructive" style={styles.centerStateText}>
                {fetchError}
              </Body>
              <Pressable
                onPress={refresh}
                style={styles.retryButton}
                accessibilityLabel="Retry loading pricing"
                accessibilityRole="button"
              >
                <Body weight="semibold">Retry</Body>
              </Pressable>
            </View>
          )}

          {/* Success banner */}
          {showSuccess && (
            <View style={styles.successBanner}>
              <Ionicons name="checkmark-circle" size={18} color={SUCCESS_DARK} />
              <Body weight="semibold" color={SUCCESS_DARK}>
                Purchase complete!
              </Body>
            </View>
          )}

          {/* Pro subscription */}
          {showProCard && proOption != null && (
            <View style={styles.section}>
              <Label>Go Pro</Label>
              <PremiumCard
                premium={proOption}
                onSubscribe={subscribe}
                isLoading={purchasingId === PURCHASING_PREMIUM_ID}
                disabled={
                  isPurchasing && purchasingId !== PURCHASING_PREMIUM_ID
                }
              />
            </View>
          )}

          {/* Contact support state */}
          {!isFetching && !fetchError && cta?.type === "contact_support" && (
            <View style={styles.centerState}>
              <Body color="secondary" style={styles.centerStateText}>
                Your account needs a quick review. Please contact support.
              </Body>
            </View>
          )}

          {/* Pro + insufficient — maxed until next refill */}
          {!isFetching && !fetchError && cta?.type === "wait_for_refill" && (
            <View style={styles.centerState}>
              <Body color="secondary" style={styles.centerStateText}>
                You&rsquo;re all set on Pro — credits refresh on the next
                billing period.
              </Body>
            </View>
          )}

          {/* Empty state — no options available */}
          {!isFetching &&
            !fetchError &&
            entitlement &&
            !showProCard &&
            cta?.type !== "contact_support" &&
            cta?.type !== "wait_for_refill" && (
              <View style={styles.centerState}>
                <Body color="secondary" style={styles.centerStateText}>
                  No purchase options available right now.
                </Body>
              </View>
            )}
        </ScrollView>
      </Animated.View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: THEME.colors.backdrop,
  },
  sheet: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    maxHeight: "85%",
    backgroundColor: THEME.colors.glass,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    borderCurve: "continuous",
    borderTopWidth: 1,
    borderTopColor: THEME.colors.glassBorder,
    paddingTop: THEME.spacing.sm,
    paddingBottom: THEME.spacing.xxxl + THEME.spacing.sm,
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: THEME.colors.textDisabled,
    alignSelf: "center",
    marginBottom: THEME.spacing.md,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.xl,
    marginBottom: THEME.spacing.md,
  },
  closeButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  badgeRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: THEME.spacing.xl,
    marginBottom: THEME.spacing.sm,
    gap: THEME.spacing.md,
  },
  ctaRow: {
    paddingHorizontal: THEME.spacing.xl,
    marginBottom: THEME.spacing.lg,
    gap: THEME.spacing.xs,
  },
  scrollContent: {
    flex: 1,
  },
  scrollContentContainer: {
    paddingHorizontal: THEME.spacing.xl,
    paddingBottom: THEME.spacing.xl,
  },
  section: {
    marginBottom: THEME.spacing.xxl,
    gap: THEME.spacing.md,
  },
  centerState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.xxxl + THEME.spacing.sm,
    gap: THEME.spacing.md,
  },
  centerStateText: {
    textAlign: "center",
  },
  retryButton: {
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.md,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.pill,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  successBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: THEME.colors.successBg,
    borderRadius: THEME.radius.md,
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.lg,
  },
});
