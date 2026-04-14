/**
 * PlanCard — current-plan summary on the subscription screen.
 *
 * Shows tier icon, tier name, contextual subtitle, stats row
 * (credits, trial remaining, billing date), trial progress bar
 * for FREE users, and the cancel link for active premium subs.
 *
 * Pure presentational component — purchase + cancel actions are
 * driven by `usePurchaseFlow` in the parent screen.
 */
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { Caption, Heading } from "../ui/Text";
import { LoadingSkeleton } from "../ui/LoadingSkeleton";
import { PressableScale } from "../ui/PressableScale";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import type { EntitlementState } from "../../lib/entitlement";

type IoniconName = React.ComponentProps<typeof Ionicons>["name"];

interface TierConfig {
  label: string;
  icon: IoniconName;
  description: (
    trialRemaining: number,
    trialLimit: number,
  ) => string;
}

const TIER_FREE = "FREE";
const TIER_CREDITS = "CREDITS";
const TIER_PREMIUM = "PREMIUM";

const SUBSCRIPTION_STATUS_ACTIVE = "active";
const SUBSCRIPTION_STATUS_CANCELING = "canceling";

/** Min trial bar width so progress is visible even at 0%. */
const TRIAL_BAR_MIN_PERCENT = 5;
const TRIAL_BAR_HEIGHT = 6;
const TRIAL_BAR_RADIUS = 3;
const PLAN_ICON_SIZE = 56;
const PLAN_ICON_GLYPH_SIZE = 28;
const STAT_NUMBER_FONT_SIZE = 20;
const TRIAL_LABEL_FONT_SIZE = 12;
const TRIAL_LABEL_LETTER_SPACING = 0.2;
const CARD_BORDER_WIDTH = 1.5;

const TIER_CONFIG: Record<string, TierConfig> = {
  [TIER_FREE]: {
    label: "Free",
    icon: "leaf-outline",
    description: (trialRemaining) =>
      trialRemaining > 0
        ? `${trialRemaining} free ${trialRemaining === 1 ? "analysis" : "analyses"} remaining`
        : "Trial expired -- upgrade to continue",
  },
  [TIER_CREDITS]: {
    label: "Credits",
    icon: "diamond-outline",
    description: () => "Pay-as-you-go with credit packs",
  },
  [TIER_PREMIUM]: {
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

/** Skeleton dimensions tuned to mirror the loaded card. */
const SKELETON_TITLE_HEIGHT = 22;
const SKELETON_SUBTITLE_HEIGHT = 14;
const SKELETON_STAT_HEIGHT = 56;
const SKELETON_TITLE_WIDTH = "60%" as const;
const SKELETON_SUBTITLE_WIDTH = "80%" as const;
const SKELETON_STAT_WIDTH = "48%" as const;

/** Skeleton placeholder for the subscription screen's loading state. */
export function PlanCardSkeleton() {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <LoadingSkeleton
          height={PLAN_ICON_SIZE}
          width={PLAN_ICON_SIZE}
          borderRadius={THEME.radius.md}
        />
        <View style={[styles.info, { gap: THEME.spacing.sm }]}>
          <LoadingSkeleton height={SKELETON_TITLE_HEIGHT} width={SKELETON_TITLE_WIDTH} />
          <LoadingSkeleton height={SKELETON_SUBTITLE_HEIGHT} width={SKELETON_SUBTITLE_WIDTH} />
        </View>
      </View>
      <View style={styles.statsRow}>
        <LoadingSkeleton
          height={SKELETON_STAT_HEIGHT}
          width={SKELETON_STAT_WIDTH}
          borderRadius={THEME.radius.md}
        />
        <LoadingSkeleton
          height={SKELETON_STAT_HEIGHT}
          width={SKELETON_STAT_WIDTH}
          borderRadius={THEME.radius.md}
        />
      </View>
    </View>
  );
}

interface PlanCardProps {
  entitlement: EntitlementState;
  isCancelling: boolean;
  onCancel: () => void;
}

export function PlanCard({ entitlement, isCancelling, onCancel }: PlanCardProps) {
  const { theme } = useTheme();

  const tier = entitlement.tier?.toUpperCase() ?? TIER_FREE;
  const tierMeta = tierConfig(tier);
  const isPremium = tier === TIER_PREMIUM;
  const trialRemaining = entitlement.trial_analyses_remaining;
  const trialLimit = entitlement.trial_analyses_limit;
  const creditBalance = entitlement.credit_balance;
  const billingEnd = entitlement.billing_period_end;
  const subscriptionStatus = entitlement.subscription_status;

  const subtitle = isPremium
    ? subscriptionStatus === SUBSCRIPTION_STATUS_ACTIVE
      ? "Active subscription"
      : subscriptionStatus === SUBSCRIPTION_STATUS_CANCELING
        ? "Cancels at period end"
        : "Active"
    : tierMeta.description(trialRemaining, trialLimit);

  const trialUsed = Math.max(0, trialLimit - trialRemaining);
  const trialPercent =
    trialLimit > 0 ? (trialUsed / trialLimit) * 100 : 0;
  const trialBarPercent =
    trialPercent > 0 ? Math.max(TRIAL_BAR_MIN_PERCENT, trialPercent) : 0;
  const trialBarWidth = `${trialBarPercent}%` as const;

  return (
    <View
      style={[
        styles.card,
        {
          borderColor: theme.accent + THEME.alpha.med,
          ...THEME.shadow.glow(theme.accent),
        },
      ]}
    >
      {/* Header */}
      <View style={styles.header}>
        <View
          style={[
            styles.iconBg,
            { backgroundColor: theme.accentMuted },
          ]}
        >
          <Ionicons
            name={tierMeta.icon}
            size={PLAN_ICON_GLYPH_SIZE}
            color={theme.accent}
          />
        </View>
        <View style={styles.info}>
          <Heading size="md">{tierMeta.label} Plan</Heading>
          <Caption style={styles.subtitle}>{subtitle}</Caption>
        </View>
      </View>

      {/* Stats row */}
      <View style={styles.statsRow}>
        {!isPremium && (
          <View style={styles.statBox}>
            <Text style={[styles.statNumber, { color: theme.accent }]}>
              {creditBalance}
            </Text>
            <Caption>Credits</Caption>
          </View>
        )}
        {tier === TIER_FREE && (
          <View style={styles.statBox}>
            <Text style={[styles.statNumber, { color: theme.accent }]}>
              {trialRemaining}
            </Text>
            <Caption>Trial Left</Caption>
          </View>
        )}
        {isPremium && (
          <View style={styles.statBox}>
            <Text style={[styles.statNumber, { color: theme.accent }]}>
              Unlimited
            </Text>
            <Caption>Generations</Caption>
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
            <Caption>
              {subscriptionStatus === SUBSCRIPTION_STATUS_CANCELING
                ? "Expires"
                : "Renews"}
            </Caption>
          </View>
        )}
      </View>

      {/* Trial timeline for free users */}
      {tier === TIER_FREE && trialLimit > 0 && (
        <View style={styles.trialTimeline}>
          <View style={styles.trialBarBg}>
            <View
              style={[
                styles.trialBarFill,
                { backgroundColor: theme.accent, width: trialBarWidth },
              ]}
            />
          </View>
          <Caption color="muted" style={styles.trialBarLabel}>
            {trialRemaining > 0
              ? `${trialUsed} of ${trialLimit} trial analyses used`
              : "Trial complete -- upgrade below"}
          </Caption>
        </View>
      )}

      {/* Cancel for premium users */}
      {isPremium && subscriptionStatus === SUBSCRIPTION_STATUS_ACTIVE && (
        <PressableScale
          onPress={onCancel}
          disabled={isCancelling}
          style={[styles.cancelLink, isCancelling && styles.cancelLinkDisabled]}
          accessibilityLabel="Cancel subscription"
          accessibilityRole="button"
        >
          {isCancelling ? (
            <ActivityIndicator
              color={THEME.colors.textSecondary}
              size="small"
            />
          ) : (
            <Caption weight="medium" style={styles.cancelLinkText}>
              Cancel subscription
            </Caption>
          )}
        </PressableScale>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: CARD_BORDER_WIDTH,
    borderColor: THEME.colors.glassBorder,
    padding: THEME.spacing.xl,
    ...THEME.shadow.glass,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.lg,
    marginBottom: THEME.spacing.xl,
  },
  iconBg: {
    width: PLAN_ICON_SIZE,
    height: PLAN_ICON_SIZE,
    borderRadius: THEME.radius.md,
    alignItems: "center",
    justifyContent: "center",
  },
  info: {
    flex: 1,
  },
  subtitle: {
    marginTop: THEME.spacing.xs / 2,
  },
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
    fontSize: STAT_NUMBER_FONT_SIZE,
    letterSpacing: 0,
    fontVariant: ["tabular-nums"],
  },
  trialTimeline: {
    marginTop: THEME.spacing.lg,
    gap: THEME.spacing.sm,
  },
  trialBarBg: {
    height: TRIAL_BAR_HEIGHT,
    borderRadius: TRIAL_BAR_RADIUS,
    backgroundColor: THEME.colors.surface,
    overflow: "hidden",
  },
  trialBarFill: {
    height: "100%",
    borderRadius: TRIAL_BAR_RADIUS,
  },
  trialBarLabel: {
    fontSize: TRIAL_LABEL_FONT_SIZE,
    letterSpacing: TRIAL_LABEL_LETTER_SPACING,
  },
  cancelLink: {
    alignSelf: "center",
    marginTop: THEME.spacing.lg,
    paddingVertical: THEME.spacing.sm,
    minHeight: MIN_TOUCH_TARGET,
    justifyContent: "center",
  },
  cancelLinkDisabled: {
    opacity: 0.5,
  },
  cancelLinkText: {
    textDecorationLine: "underline",
  },
});
