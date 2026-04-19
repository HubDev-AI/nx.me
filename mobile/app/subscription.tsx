/**
 * Subscription screen — view current plan, credit balance, upgrade options.
 *
 * Route: /subscription (Stack.Screen)
 * Auth: required — fetches GET /v1/entitlement for tier + balance + purchase options.
 *
 * Tiers: FREE, CREDITS, PREMIUM.
 *
 * Orchestration only — purchase + cancel + entitlement fetching live in
 * `usePurchaseFlow`; rendering lives in `PlanCard` / `PremiumUpsell` /
 * `CreditPackGrid`.
 */
import { useState, useCallback } from "react";
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { useRouter } from "expo-router";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import Animated from "react-native-reanimated";

import { THEME } from "../constants/theme";
import { PageBackground } from "../components/ui/PageBackground";
import {
  HeaderBackButton,
  HeaderBackButtonSpacer,
} from "../components/ui/HeaderBackButton";
import { Heading } from "../components/ui/Text";
import { useEntering } from "../lib/hooks/use-entering";
import {
  PURCHASING_PREMIUM_ID,
  usePurchaseFlow,
} from "../lib/hooks/use-purchase-flow";
import { PlanCard, PlanCardSkeleton } from "../components/subscription/PlanCard";
import { PremiumUpsell } from "../components/subscription/PremiumUpsell";
import { CreditPackGrid } from "../components/subscription/CreditPackGrid";
import { CancelSubscriptionSheet } from "../components/subscription/CancelSubscriptionSheet";
import {
  SubscriptionEmptyHint,
  SubscriptionErrorState,
} from "../components/subscription/SubscriptionStates";

const TIER_PRO = "Pro";

const ENTRANCE_DELAY_PLAN_MS = 0;
const ENTRANCE_DELAY_PREMIUM_MS = 60;
const ENTRANCE_DELAY_PACKS_MS = 120;
const ENTRANCE_DURATION_MS = 240;

const HEADER_TITLE_FONT_SIZE = 20;
const PAGE_OVERLAY_OPACITY = 0.88;

const HINT_LOADING = "Purchase options are loading. Pull down to refresh.";
const ERROR_LOAD = "We couldn't load your subscription info. Try again.";

export default function SubscriptionScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { fadeInDown } = useEntering();

  const {
    entitlement,
    isLoading,
    error,
    purchasingId,
    isCancelling,
    isCancelSheetOpen,
    refresh,
    buyCredits,
    subscribe,
    openCancelSheet,
    dismissCancelSheet,
    confirmCancel,
  } = usePurchaseFlow();

  const [isRefreshing, setIsRefreshing] = useState(false);
  const handleRefresh = useCallback(async () => {
    setIsRefreshing(true);
    try {
      await refresh();
    } finally {
      setIsRefreshing(false);
    }
  }, [refresh]);

  const tier = entitlement?.tier ?? "Free";
  const isPro = tier === TIER_PRO;
  const purchaseOptions = entitlement?.purchase_options;
  const packOption = purchaseOptions?.pack ?? null;
  const proOption = purchaseOptions?.pro ?? null;

  const isSubscribing = purchasingId === PURCHASING_PREMIUM_ID;
  const showHint = !isPro && proOption == null && packOption == null;
  const hintMessage = HINT_LOADING;

  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={PAGE_OVERLAY_OPACITY} />

      {/* Custom header with back button */}
      <View style={[styles.header, { paddingTop: insets.top }]}>
        <HeaderBackButton onPress={() => router.back()} />
        <Heading
          size="md"
          style={styles.headerTitle}
          maxFontSizeMultiplier={1.3}
        >
          Subscription
        </Heading>
        <HeaderBackButtonSpacer />
      </View>

      {isLoading ? (
        <View
          style={[
            styles.scrollContent,
            { paddingBottom: insets.bottom + THEME.spacing.xxxl },
          ]}
        >
          <PlanCardSkeleton />
        </View>
      ) : error ? (
        <View style={{ flex: 1, paddingBottom: insets.bottom }}>
          <SubscriptionErrorState message={error ?? ERROR_LOAD} onRetry={refresh} />
        </View>
      ) : entitlement ? (
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={[
            styles.scrollContent,
            { paddingBottom: insets.bottom + THEME.spacing.xxxl },
          ]}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={isRefreshing}
              onRefresh={handleRefresh}
              tintColor={THEME.colors.textSecondary}
            />
          }
        >
          <Animated.View
            entering={fadeInDown(ENTRANCE_DELAY_PLAN_MS, ENTRANCE_DURATION_MS)}
          >
            <PlanCard
              entitlement={entitlement}
              isCancelling={isCancelling}
              onCancel={openCancelSheet}
            />
          </Animated.View>

          {!isPro && proOption != null && (
            <Animated.View
              entering={fadeInDown(
                ENTRANCE_DELAY_PREMIUM_MS,
                ENTRANCE_DURATION_MS,
              )}
            >
              <PremiumUpsell
                premium={proOption}
                isSubscribing={isSubscribing}
                onSubscribe={subscribe}
              />
            </Animated.View>
          )}

          {packOption != null && (
            <Animated.View
              entering={fadeInDown(
                ENTRANCE_DELAY_PACKS_MS,
                ENTRANCE_DURATION_MS,
              )}
            >
              <CreditPackGrid
                pack={packOption}
                purchasingId={purchasingId}
                onBuy={buyCredits}
              />
            </Animated.View>
          )}

          {showHint && (
            <Animated.View
              entering={fadeInDown(
                ENTRANCE_DELAY_PREMIUM_MS,
                ENTRANCE_DURATION_MS,
              )}
            >
              <SubscriptionEmptyHint message={hintMessage} />
            </Animated.View>
          )}
        </ScrollView>
      ) : (
        <View style={styles.centered}>
          <ActivityIndicator color={THEME.colors.textSecondary} size="small" />
        </View>
      )}

      <CancelSubscriptionSheet
        visible={isCancelSheetOpen}
        isCancelling={isCancelling}
        billingPeriodEnd={entitlement?.period_end ?? null}
        onConfirm={confirmCancel}
        onDismiss={dismissCancelSheet}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.sm,
    paddingBottom: THEME.spacing.sm,
  },
  headerTitle: {
    fontSize: HEADER_TITLE_FONT_SIZE,
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
  },
});
