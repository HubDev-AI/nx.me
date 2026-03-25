/**
 * PaywallModal — full paywall sheet triggered when can_generate=false.
 *
 * Fetches entitlement data (with purchase_options), displays:
 *   - Credit badge with remaining balance
 *   - Credit pack purchase options
 *   - Premium subscription card
 *
 * Purchase flow:
 *   1. User taps credit pack "Buy" or premium "Subscribe Now"
 *   2. App calls POST /credits/purchase or POST /subscriptions
 *   3. Backend returns checkout_url (Stripe Checkout session)
 *   4. App opens Stripe Payment Sheet via initPaymentSheet + presentPaymentSheet
 *   5. On success: re-fetch entitlement, animate credit badge update
 *
 * Modal UX: scale+fade entry from trigger, swipe-down dismiss, 40-60% scrim.
 */
import { useState, useEffect, useCallback, useRef } from "react";
import {
  View,
  Text,
  Modal,
  Pressable,
  ScrollView,
  Animated,
  ActivityIndicator,
  StyleSheet,
  PanResponder,
  AccessibilityInfo,
  Linking,
  useWindowDimensions,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { SUCCESS_DARK } from "../../constants/colors";
import { FONTS } from "../../hooks/useFonts";
import { PAYWALL_ANIMATION, MIN_TOUCH_TARGET } from "../../constants/config";
import {
  fetchEntitlement,
  purchaseCredits,
  createSubscription,
} from "../../lib/entitlement";
import type {
  EntitlementState,
  CreditPackOption,
} from "../../lib/entitlement";
import { CreditBadge } from "./CreditBadge";
import { CreditPackCard } from "./CreditPackCard";
import { PremiumCard } from "./PremiumCard";

const SWIPE_DISMISS_THRESHOLD = 100;

interface PaywallModalProps {
  visible: boolean;
  onClose: () => void;
  /** Called after a successful purchase with updated entitlement state. */
  onPurchaseComplete?: (state: EntitlementState) => void;
}

type PurchaseState = "idle" | "loading" | "success" | "error";

export function PaywallModal({
  visible,
  onClose,
  onPurchaseComplete,
}: PaywallModalProps) {
  const { height: SCREEN_HEIGHT } = useWindowDimensions();

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  const [entitlement, setEntitlement] = useState<EntitlementState | null>(null);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [isFetching, setIsFetching] = useState(false);

  const [purchaseState, setPurchaseState] = useState<PurchaseState>("idle");
  const [purchaseError, setPurchaseError] = useState<string | null>(null);
  /** Track which pack is being purchased (null = subscription in progress) */
  const [activePurchaseId, setActivePurchaseId] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Focus management refs
  // ---------------------------------------------------------------------------
  const closeButtonRef = useRef<React.ElementRef<typeof Pressable>>(null);

  // ---------------------------------------------------------------------------
  // Animation refs
  // ---------------------------------------------------------------------------
  const backdropOpacity = useRef(new Animated.Value(0)).current;
  const sheetTranslateY = useRef(new Animated.Value(SCREEN_HEIGHT)).current;
  const sheetScale = useRef(new Animated.Value(0.95)).current;
  const panY = useRef(new Animated.Value(0)).current;

  // ---------------------------------------------------------------------------
  // Swipe-down to dismiss via PanResponder
  // ---------------------------------------------------------------------------
  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => false,
      onMoveShouldSetPanResponder: (_, gestureState) =>
        gestureState.dy > 10,
      onPanResponderMove: (_, gestureState) => {
        if (gestureState.dy > 0) {
          panY.setValue(gestureState.dy);
        }
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dy > SWIPE_DISMISS_THRESHOLD) {
          handleClose();
        } else {
          Animated.spring(panY, {
            toValue: 0,
            useNativeDriver: true,
            tension: 40,
            friction: 7,
          }).start();
        }
      },
    }),
  ).current;

  // ---------------------------------------------------------------------------
  // Open / close animations
  // ---------------------------------------------------------------------------
  const animateIn = useCallback(() => {
    sheetTranslateY.setValue(60);
    sheetScale.setValue(0.95);
    backdropOpacity.setValue(0);
    panY.setValue(0);

    Animated.parallel([
      Animated.timing(backdropOpacity, {
        toValue: PAYWALL_ANIMATION.SCRIM_OPACITY,
        duration: PAYWALL_ANIMATION.ENTER_DURATION_MS,
        useNativeDriver: true,
      }),
      Animated.timing(sheetTranslateY, {
        toValue: 0,
        duration: PAYWALL_ANIMATION.ENTER_DURATION_MS,
        useNativeDriver: true,
      }),
      Animated.timing(sheetScale, {
        toValue: 1,
        duration: PAYWALL_ANIMATION.ENTER_DURATION_MS,
        useNativeDriver: true,
      }),
    ]).start();
  }, [backdropOpacity, sheetTranslateY, sheetScale, panY]);

  const animateOut = useCallback(
    (callback: () => void) => {
      Animated.parallel([
        Animated.timing(backdropOpacity, {
          toValue: 0,
          duration: PAYWALL_ANIMATION.EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(sheetTranslateY, {
          toValue: 60,
          duration: PAYWALL_ANIMATION.EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
        Animated.timing(sheetScale, {
          toValue: 0.95,
          duration: PAYWALL_ANIMATION.EXIT_DURATION_MS,
          useNativeDriver: true,
        }),
      ]).start(callback);
    },
    [backdropOpacity, sheetTranslateY, sheetScale],
  );

  // ---------------------------------------------------------------------------
  // Fetch entitlement on open + accessibility announcement
  // ---------------------------------------------------------------------------
  useEffect(() => {
    if (visible) {
      animateIn();
      loadEntitlement();
      AccessibilityInfo.announceForAccessibility("Dialog opened");
      // Move focus to close button so screen readers enter the modal
      closeButtonRef.current?.focus();
    }
  }, [visible, animateIn, loadEntitlement]);

  const loadEntitlement = useCallback(async () => {
    setIsFetching(true);
    setFetchError(null);
    try {
      const state = await fetchEntitlement();
      setEntitlement(state);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load pricing";
      setFetchError(message);
    } finally {
      setIsFetching(false);
    }
  }, []);

  // ---------------------------------------------------------------------------
  // Close handler
  // ---------------------------------------------------------------------------
  const handleClose = useCallback(() => {
    if (purchaseState === "loading") return; // prevent close during purchase
    animateOut(() => {
      setPurchaseState("idle");
      setPurchaseError(null);
      setActivePurchaseId(null);
      onClose();
    });
  }, [purchaseState, animateOut, onClose]);

  // ---------------------------------------------------------------------------
  // Purchase flow: credit pack
  // ---------------------------------------------------------------------------
  const handleCreditPurchase = useCallback(
    async (pack: CreditPackOption) => {
      setPurchaseState("loading");
      setPurchaseError(null);
      setActivePurchaseId(pack.pack_id);

      try {
        // 1. Get checkout URL from backend
        const { checkout_url } = await purchaseCredits(pack.pack_id);

        // TODO: Backend returns a Stripe Checkout Session URL, not a PaymentIntent
        // client secret. The Payment Sheet requires a paymentIntentClientSecret.
        // When the backend is updated to return a payment_intent_client_secret,
        // replace the Linking.openURL fallback with initPaymentSheet + presentPaymentSheet.
        // For now, open the Stripe-hosted checkout page in the browser.
        await Linking.openURL(checkout_url);

        // Re-fetch entitlement after returning from checkout.
        // The user may have completed or cancelled payment externally.
        const updatedState = await fetchEntitlement();
        setEntitlement(updatedState);
        setPurchaseState("success");
        onPurchaseComplete?.(updatedState);
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Purchase failed";
        setPurchaseError(message);
        setPurchaseState("error");
      } finally {
        setActivePurchaseId(null);
      }
    },
    [onPurchaseComplete],
  );

  // ---------------------------------------------------------------------------
  // Purchase flow: premium subscription
  // ---------------------------------------------------------------------------
  const handleSubscribe = useCallback(async () => {
    setPurchaseState("loading");
    setPurchaseError(null);
    setActivePurchaseId(null); // null signals subscription (not a credit pack)

    try {
      const response = await createSubscription();

      if (response.status === "already_subscribed") {
        setPurchaseState("idle");
        // Re-fetch to get current state
        const updatedState = await fetchEntitlement();
        setEntitlement(updatedState);
        onPurchaseComplete?.(updatedState);
        return;
      }

      if (!response.checkout_url) {
        setPurchaseError("Subscription not available at this time.");
        setPurchaseState("error");
        return;
      }

      // TODO: Backend returns a Stripe Checkout Session URL, not a PaymentIntent
      // client secret. When the backend is updated to return a payment_intent_client_secret,
      // replace the Linking.openURL fallback with initPaymentSheet + presentPaymentSheet.
      await Linking.openURL(response.checkout_url);

      // Re-fetch entitlement after returning from checkout
      const updatedState = await fetchEntitlement();
      setEntitlement(updatedState);
      setPurchaseState("success");
      onPurchaseComplete?.(updatedState);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Subscription failed";
      setPurchaseError(message);
      setPurchaseState("error");
    }
  }, [onPurchaseComplete]);

  // ---------------------------------------------------------------------------
  // Derived state
  // ---------------------------------------------------------------------------
  const isPurchasing = purchaseState === "loading";
  const creditBalance = entitlement?.credit_balance ?? 0;
  const purchaseOptions = entitlement?.purchase_options;
  const hasCreditPacks =
    purchaseOptions?.credit_packs && purchaseOptions.credit_packs.length > 0;
  const hasPremium = purchaseOptions?.premium != null;

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------
  return (
    <Modal
      visible={visible}
      transparent
      animationType="none"
      onRequestClose={handleClose}
      statusBarTranslucent
    >
      {/* Scrim backdrop */}
      <Animated.View
        style={[styles.backdrop, { opacity: backdropOpacity }]}
      >
        <Pressable
          style={StyleSheet.absoluteFill}
          onPress={handleClose}
          accessibilityLabel="Close paywall"
          accessibilityRole="button"
        />
      </Animated.View>

      {/* Sheet */}
      <Animated.View
        style={[
          styles.sheet,
          {
            transform: [
              { translateY: Animated.add(sheetTranslateY, panY) },
              { scale: sheetScale },
            ],
          },
        ]}
        {...panResponder.panHandlers}
      >
        {/* Drag handle */}
        <View style={styles.handleBar} />

        {/* Header */}
        <View style={styles.header}>
          <Text style={styles.headerTitle}>Get More Generations</Text>
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
          <CreditBadge balance={creditBalance} />
          {entitlement && (
            <Text style={styles.badgeHint}>
              {entitlement.can_generate
                ? "You can generate"
                : "No credits remaining"}
            </Text>
          )}
        </View>

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
              <Text style={styles.stateText}>Loading pricing...</Text>
            </View>
          )}

          {/* Error state */}
          {fetchError && !isFetching && (
            <View style={styles.centerState}>
              <Ionicons name="alert-circle" size={32} color={THEME.colors.destructive} />
              <Text style={styles.errorText}>{fetchError}</Text>
              <Pressable
                onPress={loadEntitlement}
                style={styles.retryButton}
                accessibilityLabel="Retry loading pricing"
                accessibilityRole="button"
              >
                <Text style={styles.retryText}>Retry</Text>
              </Pressable>
            </View>
          )}

          {/* Purchase error banner */}
          {purchaseError && (
            <View style={styles.errorBanner} accessibilityRole="alert">
              <Ionicons name="alert-circle" size={18} color={THEME.colors.destructive} />
              <Text style={styles.errorBannerText}>{purchaseError}</Text>
            </View>
          )}

          {/* Success banner */}
          {purchaseState === "success" && (
            <View style={styles.successBanner}>
              <Ionicons name="checkmark-circle" size={18} color={SUCCESS_DARK} />
              <Text style={styles.successBannerText}>
                Purchase complete!
              </Text>
            </View>
          )}

          {/* Credit packs */}
          {!isFetching && !fetchError && hasCreditPacks && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Credit Packs</Text>
              <View style={styles.packList}>
                {purchaseOptions!.credit_packs.map((pack) => (
                  <CreditPackCard
                    key={pack.pack_id}
                    pack={pack}
                    onPurchase={handleCreditPurchase}
                    isLoading={
                      isPurchasing && activePurchaseId === pack.pack_id
                    }
                    disabled={
                      isPurchasing && activePurchaseId !== pack.pack_id
                    }
                  />
                ))}
              </View>
            </View>
          )}

          {/* Premium subscription */}
          {!isFetching && !fetchError && hasPremium && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Go Premium</Text>
              <PremiumCard
                onSubscribe={handleSubscribe}
                isLoading={isPurchasing && activePurchaseId === null}
                disabled={isPurchasing && activePurchaseId !== null}
              />
            </View>
          )}

          {/* Empty state — no options available */}
          {!isFetching &&
            !fetchError &&
            entitlement &&
            !hasCreditPacks &&
            !hasPremium && (
              <View style={styles.centerState}>
                <Text style={styles.stateText}>
                  No purchase options available right now.
                </Text>
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
    backgroundColor: "#000000",
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
    borderTopWidth: 1,
    borderTopColor: THEME.colors.glassBorder,
    paddingTop: THEME.spacing.sm,
    paddingBottom: 40,
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
  headerTitle: {
    fontFamily: FONTS.display,
    color: THEME.colors.textPrimary,
    ...THEME.typography.heading,
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
    marginBottom: THEME.spacing.lg,
    gap: THEME.spacing.md,
  },
  badgeHint: {
    fontFamily: FONTS.bodyMedium,
    color: THEME.colors.textSecondary,
    ...THEME.typography.caption,
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
  sectionTitle: {
    fontFamily: FONTS.bodySemiBold,
    color: THEME.colors.textSecondary,
    fontSize: 13,
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  packList: {
    gap: THEME.spacing.md,
  },
  centerState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: THEME.spacing.xxxl + THEME.spacing.sm,
    gap: THEME.spacing.md,
  },
  stateText: {
    fontFamily: FONTS.body,
    color: THEME.colors.textSecondary,
    ...THEME.typography.body,
    textAlign: "center",
  },
  errorText: {
    fontFamily: FONTS.body,
    color: THEME.colors.destructive,
    ...THEME.typography.body,
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
  retryText: {
    fontFamily: FONTS.bodySemiBold,
    color: THEME.colors.textPrimary,
    fontSize: 14,
  },
  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: "rgba(239, 68, 68, 0.1)",
    borderRadius: THEME.radius.md,
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.lg,
  },
  errorBannerText: {
    fontFamily: FONTS.bodyMedium,
    color: THEME.colors.destructive,
    fontSize: 14,
    flex: 1,
  },
  successBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    backgroundColor: "rgba(74,222,128,0.1)",
    borderRadius: THEME.radius.md,
    padding: THEME.spacing.md,
    marginBottom: THEME.spacing.lg,
  },
  successBannerText: {
    fontFamily: FONTS.bodySemiBold,
    color: SUCCESS_DARK,
    fontSize: 14,
  },
});
