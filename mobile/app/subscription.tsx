/**
 * Subscription screen -- view current plan, credit balance, upgrade options.
 *
 * Route: /subscription (Stack.Screen)
 * Auth: required -- fetches GET /v1/entitlement for tier + balance + purchase options.
 *
 * Tiers: FREE, CREDITS, PREMIUM
 * If on FREE: shows trial analyses remaining, credit packs, premium upsell
 * If on CREDITS: shows credit balance, option to buy more, premium upsell
 * If on PREMIUM: shows active subscription details, option to cancel
 */
import { useState, useEffect, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  Pressable,
  ActivityIndicator,
  Alert,
  Linking,
  StyleSheet,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated from "react-native-reanimated";

import { THEME } from "../constants/theme";
import { PageBackground } from "../components/ui/PageBackground";
import { PressableScale } from "../components/ui/PressableScale";
import { LoadingSkeleton } from "../components/ui/LoadingSkeleton";
import { useEntering } from "../lib/hooks/use-entering";
import { useTheme } from "../lib/theme-context";
import { FONTS } from "../hooks/useFonts";
import { MIN_TOUCH_TARGET } from "../constants/config";
import {
  fetchEntitlement,
  purchaseCredits,
  createSubscription,
  type EntitlementState,
  type CreditPackOption,
} from "../lib/entitlement";
import { apiFetch } from "../lib/api";
import { parseApiError } from "../lib/errors";
import { showToast } from "../lib/toast";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type IoniconName = React.ComponentProps<typeof Ionicons>["name"];

/** Server returns this status when re-subscribing on an already-active plan. */
const STATUS_ALREADY_SUBSCRIBED = "already_subscribed";

interface TierConfig {
  label: string;
  icon: IoniconName;
  description: (trialRemaining: number) => string;
}

const TIER_CONFIG: Record<string, TierConfig> = {
  FREE: {
    label: "Free",
    icon: "leaf-outline",
    description: (trialRemaining) =>
      trialRemaining > 0
        ? `${trialRemaining} free ${trialRemaining === 1 ? "analysis" : "analyses"} remaining`
        : "Trial expired -- upgrade to continue",
  },
  CREDITS: {
    label: "Credits",
    icon: "flash",
    description: () => "Pay-as-you-go with credit packs",
  },
  PREMIUM: {
    label: "Premium",
    icon: "diamond",
    description: () => "Unlimited analyses & priority processing",
  },
};

const DEFAULT_TIER: TierConfig = {
  label: "Plan",
  icon: "leaf-outline",
  description: () => "Your current tier",
};

function tierConfig(tier: string): TierConfig {
  return TIER_CONFIG[tier.toUpperCase()] ?? { ...DEFAULT_TIER, label: tier };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SubscriptionScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { theme } = useTheme();
  const { fadeInDown } = useEntering();

  const [entitlement, setEntitlement] = useState<EntitlementState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [purchasingId, setPurchasingId] = useState<string | null>(null);
  const [isSubscribing, setIsSubscribing] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  // -------------------------------------------------------------------------
  // Entitlement refresh — shared by initial load and all post-action refetches.
  // -------------------------------------------------------------------------
  const refreshEntitlement = useCallback(async () => {
    const updated = await fetchEntitlement();
    setEntitlement(updated);
  }, []);

  const loadEntitlement = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await refreshEntitlement();
    } catch {
      setError("We couldn't load your subscription info. Try again.");
    } finally {
      setIsLoading(false);
    }
  }, [refreshEntitlement]);

  useEffect(() => {
    loadEntitlement();
  }, [loadEntitlement]);

  // -------------------------------------------------------------------------
  // Purchase credit pack
  // -------------------------------------------------------------------------
  const handleBuyCredits = useCallback(async (pack: CreditPackOption) => {
    setPurchasingId(pack.pack_id);
    try {
      const { checkout_url } = await purchaseCredits(pack.pack_id);
      await Linking.openURL(checkout_url);
      await refreshEntitlement();
    } catch (err) {
      const appError = parseApiError(err);
      showToast({ kind: 'error', message: appError.message });
    } finally {
      setPurchasingId(null);
    }
  }, [refreshEntitlement]);

  // -------------------------------------------------------------------------
  // Subscribe to premium
  // -------------------------------------------------------------------------
  const handleSubscribe = useCallback(async () => {
    setIsSubscribing(true);
    try {
      const response = await createSubscription();

      if (response.status === STATUS_ALREADY_SUBSCRIBED) {
        await refreshEntitlement();
        return;
      }

      if (!response.checkout_url) {
        showToast({ kind: 'warning', message: "Subscription is not available at this time." });
        return;
      }

      await Linking.openURL(response.checkout_url);
      await refreshEntitlement();
    } catch (err) {
      const appError = parseApiError(err);
      showToast({ kind: 'error', message: appError.message });
    } finally {
      setIsSubscribing(false);
    }
  }, [refreshEntitlement]);

  // -------------------------------------------------------------------------
  // Cancel subscription
  // -------------------------------------------------------------------------
  const handleCancel = useCallback(() => {
    Alert.alert(
      "Cancel Subscription",
      "Your premium benefits will remain until the end of your billing period.",
      [
        { text: "Keep Subscription", style: "cancel" },
        {
          text: "Cancel",
          style: "destructive",
          onPress: async () => {
            setIsCancelling(true);
            try {
              await apiFetch("/v1/subscriptions", { method: "DELETE" });
              await refreshEntitlement();
            } catch (err) {
              const appError = parseApiError(err);
              showToast({ kind: 'error', message: appError.message });
            } finally {
              setIsCancelling(false);
            }
          },
        },
      ],
    );
  }, [refreshEntitlement]);

  // -------------------------------------------------------------------------
  // Derived state
  // -------------------------------------------------------------------------
  const tier = entitlement?.tier?.toUpperCase() ?? "FREE";
  const tierMeta = tierConfig(tier);
  const isPremium = tier === "PREMIUM";
  const creditBalance = entitlement?.credit_balance ?? 0;
  const trialRemaining = entitlement?.trial_analyses_remaining ?? 0;
  const purchaseOptions = entitlement?.purchase_options;
  const creditPacks = purchaseOptions?.credit_packs ?? [];
  const hasPremiumOption = purchaseOptions?.premium != null;
  const billingEnd = entitlement?.billing_period_end;

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------
  return (
      <View style={styles.container}>
        <PageBackground overlayOpacity={0.88} />

        {/* Custom header with back button */}
        <View style={[styles.header, { paddingTop: insets.top }]}>
          <Pressable
            onPress={() => router.back()}
            style={styles.backBtn}
            accessibilityLabel="Go back"
            accessibilityRole="button"
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          >
            <Ionicons name="chevron-back" size={24} color={THEME.colors.textPrimary} />
          </Pressable>
          <Text
            style={styles.headerTitle}
            maxFontSizeMultiplier={1.3}
          >
            Subscription
          </Text>
          <View style={styles.backBtn} />
        </View>

        {isLoading ? (
          <View
            style={[
              styles.scrollContent,
              { paddingTop: THEME.spacing.lg, paddingBottom: insets.bottom + THEME.spacing.xxxl },
            ]}
          >
            <View style={styles.planCard}>
              <View style={[styles.planHeader, { gap: THEME.spacing.lg }]}>
                <LoadingSkeleton height={56} width={56} borderRadius={THEME.radius.md} />
                <View style={{ flex: 1, gap: THEME.spacing.sm }}>
                  <LoadingSkeleton height={22} width="60%" />
                  <LoadingSkeleton height={14} width="80%" />
                </View>
              </View>
              <View style={[styles.statsRow, { marginTop: THEME.spacing.lg }]}>
                <LoadingSkeleton height={56} width="48%" borderRadius={THEME.radius.md} />
                <LoadingSkeleton height={56} width="48%" borderRadius={THEME.radius.md} />
              </View>
            </View>
          </View>
        ) : error ? (
          <View style={[styles.centered, { paddingBottom: insets.bottom }]}>
            <Ionicons
              name="alert-circle-outline"
              size={48}
              color={THEME.colors.destructive}
            />
            <Text style={styles.errorText}>{error}</Text>
            <Pressable
              onPress={loadEntitlement}
              style={[styles.retryButton, { backgroundColor: theme.accent }]}
              accessibilityLabel="Retry"
              accessibilityRole="button"
            >
              <Text style={styles.retryButtonText}>Retry</Text>
            </Pressable>
          </View>
        ) : (
          <ScrollView
            style={styles.scroll}
            contentContainerStyle={[
              styles.scrollContent,
              { paddingBottom: insets.bottom + THEME.spacing.xxxl },
            ]}
            showsVerticalScrollIndicator={false}
          >
            {/* ---- Current Plan Card ---- */}
            <Animated.View entering={fadeInDown(0, 240)}>
              <View
                style={[
                  styles.planCard,
                  {
                    borderColor: theme.accent + "40",
                    ...THEME.shadow.glow(theme.accent),
                  },
                ]}
              >
                <View style={styles.planHeader}>
                  <View
                    style={[
                      styles.planIconBg,
                      { backgroundColor: theme.accentMuted },
                    ]}
                  >
                    <Ionicons
                      name={tierMeta.icon}
                      size={28}
                      color={theme.accent}
                    />
                  </View>
                  <View style={styles.planInfo}>
                    <Text style={styles.planTitle}>{tierMeta.label} Plan</Text>
                    <Text style={styles.planSubtitle}>
                      {isPremium
                        ? entitlement?.subscription_status === "active"
                          ? "Active subscription"
                          : entitlement?.subscription_status === "canceling"
                            ? "Cancels at period end"
                            : "Active"
                        : tierMeta.description(trialRemaining)}
                    </Text>
                  </View>
                </View>

                {/* Stats row */}
                <View style={styles.statsRow}>
                  {!isPremium && (
                    <View style={styles.statBox}>
                      <Text style={[styles.statNumber, { color: theme.accent }]}>
                        {creditBalance}
                      </Text>
                      <Text style={styles.statLabel}>Credits</Text>
                    </View>
                  )}
                  {tier === "FREE" && (
                    <View style={styles.statBox}>
                      <Text style={[styles.statNumber, { color: theme.accent }]}>
                        {trialRemaining}
                      </Text>
                      <Text style={styles.statLabel}>Trial Left</Text>
                    </View>
                  )}
                  {isPremium && (
                    <View style={styles.statBox}>
                      <Text style={[styles.statNumber, { color: theme.accent }]}>
                        Unlimited
                      </Text>
                      <Text style={styles.statLabel}>Generations</Text>
                    </View>
                  )}
                  {billingEnd && (
                    <View style={styles.statBox}>
                      <Text style={[styles.statNumber, { color: theme.accent }]}>
                        {new Date(billingEnd).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                        })}
                      </Text>
                      <Text style={styles.statLabel}>
                        {entitlement?.subscription_status === "canceling"
                          ? "Expires"
                          : "Renews"}
                      </Text>
                    </View>
                  )}
                </View>

                {/* Trial timeline for free users */}
                {tier === "FREE" && (
                  <View style={styles.trialTimeline}>
                    <View style={styles.trialBarBg}>
                      <View
                        style={[
                          styles.trialBarFill,
                          {
                            backgroundColor: theme.accent,
                            width: `${Math.max(
                              5,
                              ((3 - trialRemaining) / 3) * 100,
                            )}%`,
                          },
                        ]}
                      />
                    </View>
                    <Text style={styles.trialBarLabel}>
                      {trialRemaining > 0
                        ? `${3 - trialRemaining} of 3 trial analyses used`
                        : "Trial complete -- upgrade below"}
                    </Text>
                  </View>
                )}

                {/* Cancel for premium users */}
                {isPremium &&
                  entitlement?.subscription_status === "active" && (
                    <PressableScale
                      onPress={handleCancel}
                      disabled={isCancelling}
                      style={styles.cancelLink}
                      accessibilityLabel="Cancel subscription"
                      accessibilityRole="button"
                    >
                      {isCancelling ? (
                        <ActivityIndicator
                          color={THEME.colors.textSecondary}
                          size="small"
                        />
                      ) : (
                        <Text style={styles.cancelLinkText}>
                          Cancel subscription
                        </Text>
                      )}
                    </PressableScale>
                  )}
              </View>
            </Animated.View>

            {/* ---- Premium Upsell (if not already premium) ---- */}
            {!isPremium && hasPremiumOption && (
              <Animated.View entering={fadeInDown(60, 240)}>
                <Text
                  style={styles.sectionLabel}
                  maxFontSizeMultiplier={1.3}
                >
                  RECOMMENDED
                </Text>
                <PressableScale
                  onPress={handleSubscribe}
                  disabled={isSubscribing}
                  style={[
                    styles.premiumCard,
                    {
                      borderColor: theme.accent,
                      ...THEME.shadow.glow(theme.accent),
                    },
                  ]}
                  accessibilityLabel="Subscribe to Premium"
                  accessibilityRole="button"
                >
                  <View style={styles.premiumBadge}>
                    <Ionicons name="diamond" size={16} color={theme.accent} />
                    <Text
                      style={[styles.premiumBadgeText, { color: theme.accent }]}
                    >
                      PREMIUM
                    </Text>
                  </View>
                  <Text style={styles.premiumTitle}>Go Unlimited</Text>
                  <Text style={styles.premiumDescription}>
                    Unlimited glow-up analyses, priority processing, and access
                    to Ada AI advisor chat.
                  </Text>
                  <Text style={[styles.premiumPrice, { color: theme.accent }]}>
                    {purchaseOptions?.premium?.name ?? "Premium Plan"}
                  </Text>

                  <View
                    style={[
                      styles.premiumButton,
                      { backgroundColor: theme.accent },
                    ]}
                  >
                    {isSubscribing ? (
                      <ActivityIndicator color={THEME.colors.bg} size="small" />
                    ) : (
                      <Text style={styles.premiumButtonText}>
                        Subscribe Now
                      </Text>
                    )}
                  </View>
                </PressableScale>
              </Animated.View>
            )}

            {/* ---- Credit Packs ---- */}
            {!isPremium && creditPacks.length > 0 && (
              <Animated.View entering={fadeInDown(120, 240)}>
                <Text
                  style={styles.sectionLabel}
                  maxFontSizeMultiplier={1.3}
                >
                  CREDIT PACKS
                </Text>
                <Text style={styles.sectionDescription}>
                  Buy credits to unlock individual analyses
                </Text>
                <View style={styles.packGrid}>
                  {creditPacks.map((pack, index) => {
                    const isActive = purchasingId === pack.pack_id;
                    return (
                      <Animated.View
                        key={pack.pack_id}
                        entering={fadeInDown(160 + Math.min(index, 4) * 40, 240)}
                        style={styles.packCardWrapper}
                      >
                        <PressableScale
                          onPress={() => handleBuyCredits(pack)}
                          disabled={purchasingId !== null}
                          style={[
                            styles.packCard,
                            isActive && {
                              borderColor: theme.accent + "60",
                              ...THEME.shadow.glow(theme.accent),
                            },
                          ]}
                          accessibilityLabel={`Buy ${pack.credits} credits`}
                          accessibilityRole="button"
                        >
                          <View
                            style={[
                              styles.packIconBg,
                              { backgroundColor: theme.accentMuted },
                            ]}
                          >
                            <Ionicons
                              name="flash"
                              size={22}
                              color={theme.accent}
                            />
                          </View>
                          <Text style={styles.packCredits}>
                            {pack.credits}
                          </Text>
                          <Text style={styles.packLabel}>credits</Text>
                          <View
                            style={[
                              styles.packButton,
                              { backgroundColor: theme.accentMuted },
                            ]}
                          >
                            {isActive ? (
                              <ActivityIndicator
                                color={theme.accent}
                                size="small"
                              />
                            ) : (
                              <Text
                                style={[
                                  styles.packButtonText,
                                  { color: theme.accent },
                                ]}
                              >
                                Buy
                              </Text>
                            )}
                          </View>
                        </PressableScale>
                      </Animated.View>
                    );
                  })}
                </View>
              </Animated.View>
            )}

            {/* ---- No purchase options available hint ---- */}
            {!isPremium && !hasPremiumOption && creditPacks.length === 0 && (
              <Animated.View entering={fadeInDown(60, 240)}>
                <View style={styles.hintCard}>
                  <Ionicons
                    name="information-circle-outline"
                    size={24}
                    color={THEME.colors.textSecondary}
                  />
                  <Text style={styles.hintText}>
                    {tier === "FREE" && trialRemaining > 0
                      ? "Use your free trial analyses first. Purchase options will appear when your trial ends."
                      : "Purchase options are loading. Pull down to refresh."}
                  </Text>
                </View>
              </Animated.View>
            )}
          </ScrollView>
        )}
      </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 8,
    paddingBottom: 10,
  },
  backBtn: {
    width: 44,
    height: 44,
    alignItems: "center",
    justifyContent: "center",
  },
  headerTitle: {
    fontFamily: FONTS.display,
    fontSize: 20,
    color: THEME.colors.textPrimary,
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.lg,
  },
  centered: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    padding: THEME.spacing.xxl,
    gap: THEME.spacing.md,
  },
  loadingText: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },
  errorText: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    textAlign: "center",
  },
  retryButton: {
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.xxl,
    paddingVertical: THEME.spacing.md,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    marginTop: THEME.spacing.sm,
  },
  retryButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 15,
    color: THEME.colors.bg,
  },

  // Section label
  sectionLabel: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 11,
    color: THEME.colors.textSecondary,
    letterSpacing: 1,
    textTransform: "uppercase",
    marginTop: THEME.spacing.xxl,
    marginBottom: THEME.spacing.xs,
    marginLeft: THEME.spacing.xs,
  },
  sectionDescription: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textMuted,
    marginBottom: THEME.spacing.md,
    marginLeft: THEME.spacing.xs,
  },

  // Plan card
  planCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1.5,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.xl,
    ...THEME.shadow.glass,
  },
  planHeader: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.lg,
    marginBottom: THEME.spacing.xl,
  },
  planIconBg: {
    width: 56,
    height: 56,
    borderRadius: THEME.radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  planInfo: {
    flex: 1,
  },
  planTitle: {
    fontFamily: FONTS.display,
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
  },
  planSubtitle: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    marginTop: THEME.spacing.xs / 2,
  },

  // Stats row
  statsRow: {
    flexDirection: "row",
    gap: THEME.spacing.md,
  },
  statBox: {
    flex: 1,
    backgroundColor: THEME.colors.surface,
    borderRadius: THEME.radius.md,
    padding: THEME.spacing.md,
    alignItems: "center",
    gap: THEME.spacing.xs,
  },
  statNumber: {
    fontFamily: FONTS.bodyBold,
    fontSize: 20,
    letterSpacing: 0,
    // Prevent digit-width jitter as counts change (e.g. 9 → 10).
    fontVariant: ["tabular-nums"],
  },
  statLabel: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
  },

  // Trial timeline
  trialTimeline: {
    marginTop: THEME.spacing.lg,
    gap: THEME.spacing.sm,
  },
  trialBarBg: {
    height: 6,
    borderRadius: 3,
    backgroundColor: THEME.colors.surface,
    overflow: "hidden",
  },
  trialBarFill: {
    height: "100%",
    borderRadius: 3,
  },
  trialBarLabel: {
    fontFamily: FONTS.body,
    fontSize: 12,
    color: THEME.colors.textMuted,
    letterSpacing: 0.2,
  },

  // Cancel link
  cancelLink: {
    alignSelf: "center",
    marginTop: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  cancelLinkText: {
    fontFamily: FONTS.bodyMedium,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    textDecorationLine: "underline",
  },

  // Premium upsell card
  premiumCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1.5,
    padding: THEME.spacing.xl,
  },
  premiumBadge: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    marginBottom: THEME.spacing.md,
  },
  premiumBadgeText: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 11,
    letterSpacing: 1.2,
  },
  premiumTitle: {
    fontFamily: FONTS.display,
    ...THEME.typography.heading,
    color: THEME.colors.textPrimary,
    marginBottom: THEME.spacing.sm,
  },
  premiumDescription: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    marginBottom: THEME.spacing.md,
    lineHeight: 22,
  },
  premiumPrice: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 16,
    marginBottom: THEME.spacing.xl,
  },
  premiumButton: {
    borderRadius: THEME.radius.pill,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  premiumButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 16,
    color: THEME.colors.bg,
  },

  // Credit pack grid
  packGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: THEME.spacing.md,
  },
  packCardWrapper: {
    flex: 1,
    minWidth: 140,
  },
  packCard: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.lg,
    alignItems: "center",
    gap: THEME.spacing.sm,
    ...THEME.shadow.glass,
  },
  packIconBg: {
    width: 40,
    height: 40,
    borderRadius: THEME.radius.md,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: THEME.spacing.xs,
  },
  packCredits: {
    fontFamily: FONTS.display,
    fontSize: 32,
    color: THEME.colors.textPrimary,
    lineHeight: 38,
    fontVariant: ["tabular-nums"],
  },
  packLabel: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    marginBottom: THEME.spacing.sm,
  },
  packButton: {
    borderRadius: THEME.radius.pill,
    paddingHorizontal: THEME.spacing.xxl,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
    width: "100%",
  },
  packButtonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
  },

  // Hint card
  hintCard: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: THEME.spacing.md,
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.xl,
    marginTop: THEME.spacing.xxl,
  },
  hintText: {
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textSecondary,
    flex: 1,
    lineHeight: 22,
  },
});
