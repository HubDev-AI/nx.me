/**
 * PlanCard — current-plan summary on the subscription screen.
 *
 * Shows tier icon, tier name, contextual subtitle, stats row
 * (remaining glow-ups, billing date), and the cancel link for
 * active Pro subs.
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
  description: (remainingGlowups: number) => string;
}

const TIER_FREE = "Free";
const TIER_PRO = "Pro";

const SUBSCRIPTION_STATUS_ACTIVE = "active";
const SUBSCRIPTION_STATUS_GRACE = "grace";
const SUBSCRIPTION_STATUS_CANCELED = "canceled";

const PLAN_ICON_SIZE = 56;
const PLAN_ICON_GLYPH_SIZE = 28;
const STAT_NUMBER_FONT_SIZE = 20;
const CARD_BORDER_WIDTH = 1.5;

const TIER_CONFIG: Record<string, TierConfig> = {
  [TIER_FREE]: {
    label: "Free",
    icon: "leaf-outline",
    description: (remaining) =>
      remaining > 0
        ? `${remaining} free ${remaining === 1 ? "glow-up" : "glow-ups"} remaining`
        : "No credits — upgrade to continue",
  },
  [TIER_PRO]: {
    label: "Pro",
    icon: "diamond",
    description: (remaining) =>
      remaining > 0
        ? `${remaining} glow-ups remaining this period`
        : "No credits — top up to continue",
  },
};

const DEFAULT_TIER: TierConfig = {
  label: "Plan",
  icon: "leaf-outline",
  description: () => "Your current tier",
};

function tierConfig(tier: string): TierConfig {
  return TIER_CONFIG[tier] ?? { ...DEFAULT_TIER, label: tier };
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

  const tier = entitlement.tier;
  const tierMeta = tierConfig(tier);
  const isPro = tier === TIER_PRO;
  const remainingGlowups = entitlement.remaining_glowups;
  const subscriptionStatus = entitlement.subscription_status;
  const periodEnd = entitlement.period_end;
  const graceEnd = entitlement.grace_end;

  const subtitle = isPro
    ? subscriptionStatus === SUBSCRIPTION_STATUS_ACTIVE
      ? "Active subscription"
      : subscriptionStatus === SUBSCRIPTION_STATUS_GRACE
        ? "Payment issue — update card to stay Pro"
        : subscriptionStatus === SUBSCRIPTION_STATUS_CANCELED
          ? "Cancels at period end"
          : "Active"
    : tierMeta.description(remainingGlowups);

  // Show grace_end when in grace, period_end otherwise for Pro
  const billingDateLabel =
    subscriptionStatus === SUBSCRIPTION_STATUS_GRACE && graceEnd != null
      ? graceEnd
      : periodEnd;

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
        <View style={styles.statBox}>
          <Text style={[styles.statNumber, { color: theme.accent }]}>
            {remainingGlowups}
          </Text>
          <Caption>Glow-Ups</Caption>
        </View>
        {billingDateLabel && (
          <View style={styles.statBox}>
            <Text style={[styles.statNumber, { color: theme.accent }]}>
              {new Date(billingDateLabel).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </Text>
            <Caption>
              {subscriptionStatus === SUBSCRIPTION_STATUS_GRACE
                ? "Grace ends"
                : subscriptionStatus === SUBSCRIPTION_STATUS_CANCELED
                  ? "Expires"
                  : "Renews"}
            </Caption>
          </View>
        )}
      </View>

      {/* Cancel for active Pro users */}
      {isPro && subscriptionStatus === SUBSCRIPTION_STATUS_ACTIVE && (
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
