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
  Dimensions,
  PanResponder,
  AccessibilityInfo,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useStripe } from "@stripe/stripe-react-native";

import {
  BG_PAGE,
  BG_ELEVATED,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  TEXT_DISABLED,
  ERROR_DARK,
} from "../../constants/colors";
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

const { height: SCREEN_HEIGHT } = Dimensions.get("window");
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
  const { initPaymentSheet, presentPaymentSheet } = useStripe();

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
  }, [visible, animateIn]);

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

        // 2. Initialize Stripe Payment Sheet with the checkout URL
        // The checkout_url contains the session ID; we use it as the client secret
        // for the Payment Sheet flow.
        const { error: initError } = await initPaymentSheet({
          merchantDisplayName: "NXME",
          paymentIntentClientSecret: checkout_url,
          returnURL: "nxme://payment/success",
        });

        if (initError) {
          setPurchaseState("error");
          setPurchaseError(initError.message);
          return;
        }

        // 3. Present the Payment Sheet
        const { error: presentError } = await presentPaymentSheet();

        if (presentError) {
          // User cancelled or payment failed
          setPurchaseState("idle");
          if (presentError.code !== "Canceled") {
            setPurchaseError(presentError.message);
            setPurchaseState("error");
          }
          return;
        }

        // 4. Payment succeeded — re-fetch entitlement for updated balance
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
    [initPaymentSheet, presentPaymentSheet, onPurchaseComplete],
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

      // Initialize and present Payment Sheet
      const { error: initError } = await initPaymentSheet({
        merchantDisplayName: "NXME",
        paymentIntentClientSecret: response.checkout_url,
        returnURL: "nxme://payment/success",
      });

      if (initError) {
        setPurchaseState("error");
        setPurchaseError(initError.message);
        return;
      }

      const { error: presentError } = await presentPaymentSheet();

      if (presentError) {
        setPurchaseState("idle");
        if (presentError.code !== "Canceled") {
          setPurchaseError(presentError.message);
          setPurchaseState("error");
        }
        return;
      }

      // Subscription succeeded — re-fetch entitlement
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
  }, [initPaymentSheet, presentPaymentSheet, onPurchaseComplete]);

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
            <Ionicons name="close" size={24} color={TEXT_SECONDARY} />
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
              <ActivityIndicator color={TEXT_SECONDARY} size="large" />
              <Text style={styles.stateText}>Loading pricing...</Text>
            </View>
          )}

          {/* Error state */}
          {fetchError && !isFetching && (
            <View style={styles.centerState}>
              <Ionicons name="alert-circle" size={32} color={ERROR_DARK} />
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
              <Ionicons name="alert-circle" size={18} color={ERROR_DARK} />
              <Text style={styles.errorBannerText}>{purchaseError}</Text>
            </View>
          )}

          {/* Success banner */}
          {purchaseState === "success" && (
            <View style={styles.successBanner}>
              <Ionicons name="checkmark-circle" size={18} color="#4ADE80" />
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
    maxHeight: SCREEN_HEIGHT * 0.85,
    backgroundColor: BG_PAGE,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    paddingTop: 8,
    paddingBottom: 40,
  },
  handleBar: {
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: TEXT_DISABLED,
    alignSelf: "center",
    marginBottom: 12,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    marginBottom: 12,
  },
  headerTitle: {
    color: TEXT_PRIMARY,
    fontSize: 22,
    fontWeight: "700",
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
    paddingHorizontal: 20,
    marginBottom: 16,
    gap: 12,
  },
  badgeHint: {
    color: TEXT_SECONDARY,
    fontSize: 14,
    fontWeight: "500",
  },
  scrollContent: {
    flex: 1,
  },
  scrollContentContainer: {
    paddingHorizontal: 20,
    paddingBottom: 20,
  },
  section: {
    marginBottom: 24,
    gap: 12,
  },
  sectionTitle: {
    color: TEXT_SECONDARY,
    fontSize: 13,
    fontWeight: "600",
    textTransform: "uppercase",
    letterSpacing: 0.8,
  },
  packList: {
    gap: 10,
  },
  centerState: {
    alignItems: "center",
    justifyContent: "center",
    paddingVertical: 40,
    gap: 12,
  },
  stateText: {
    color: TEXT_SECONDARY,
    fontSize: 15,
    textAlign: "center",
  },
  errorText: {
    color: ERROR_DARK,
    fontSize: 15,
    textAlign: "center",
  },
  retryButton: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    backgroundColor: BG_ELEVATED,
    borderRadius: 8,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  retryText: {
    color: TEXT_PRIMARY,
    fontSize: 14,
    fontWeight: "600",
  },
  errorBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(248,113,113,0.1)",
    borderRadius: 10,
    padding: 12,
    marginBottom: 16,
  },
  errorBannerText: {
    color: ERROR_DARK,
    fontSize: 14,
    fontWeight: "500",
    flex: 1,
  },
  successBanner: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: "rgba(74,222,128,0.1)",
    borderRadius: 10,
    padding: 12,
    marginBottom: 16,
  },
  successBannerText: {
    color: "#4ADE80",
    fontSize: 14,
    fontWeight: "600",
  },
});
