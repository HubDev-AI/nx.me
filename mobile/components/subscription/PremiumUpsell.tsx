/**
 * PremiumUpsell — RECOMMENDED block on the subscription screen.
 *
 * Pressable card that opens the Stripe Checkout subscribe flow.
 * Reads price + plan name from the backend `PremiumOption` and
 * formats via `formatPrice`.
 *
 * Billing interval assumption matches `PremiumCard`: hardcoded
 * monthly until backend exposes `recurring.interval`.
 */
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { Body, Heading, Label } from "../ui/Text";
import { PressableScale } from "../ui/PressableScale";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { formatPrice } from "../../lib/format-price";
import type { PremiumOption } from "../../lib/entitlement";

/** Suffix appended to the Premium price (e.g. "/mo"). Monthly-only for now. */
const BILLING_INTERVAL_SUFFIX = "/mo";
const PREMIUM_BADGE_ICON_SIZE = 16;
const CARD_BORDER_WIDTH = 1.5;
const BADGE_LETTER_SPACING = 1.2;
const DESCRIPTION_LINE_HEIGHT = 22;
const PRICE_FONT_SIZE = 16;
const BUTTON_FONT_SIZE = 16;

interface PremiumUpsellProps {
  premium: PremiumOption;
  isSubscribing: boolean;
  onSubscribe: () => void;
}

export function PremiumUpsell({
  premium,
  isSubscribing,
  onSubscribe,
}: PremiumUpsellProps) {
  const { theme } = useTheme();

  const formattedPrice = formatPrice(premium.amount_cents, premium.currency);

  return (
    <>
      <Label style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
        RECOMMENDED
      </Label>
      <PressableScale
        onPress={onSubscribe}
        disabled={isSubscribing}
        style={[
          styles.card,
          {
            borderColor: theme.accent,
            ...THEME.shadow.glow(theme.accent),
          },
        ]}
        accessibilityLabel={`Subscribe to ${premium.name} for ${formattedPrice} per month`}
        accessibilityRole="button"
      >
        <View style={styles.badge}>
          <Ionicons
            name="diamond"
            size={PREMIUM_BADGE_ICON_SIZE}
            color={theme.accent}
          />
          <Label color={theme.accent} style={styles.badgeText}>
            PREMIUM
          </Label>
        </View>
        <Heading size="md" style={styles.title}>
          Go Unlimited
        </Heading>
        <Body color="secondary" style={styles.description}>
          Unlimited glow-up analyses, priority processing, and access to Ada
          AI advisor chat.
        </Body>
        <Body weight="semibold" color={theme.accent} style={styles.price}>
          {premium.name} · {formattedPrice}
          {BILLING_INTERVAL_SUFFIX}
        </Body>

        <View style={[styles.button, { backgroundColor: theme.accent }]}>
          {isSubscribing ? (
            <ActivityIndicator color={THEME.colors.bg} size="small" />
          ) : (
            <Text style={styles.buttonText}>Subscribe Now</Text>
          )}
        </View>
      </PressableScale>
    </>
  );
}

const styles = StyleSheet.create({
  sectionLabel: {
    marginTop: THEME.spacing.xxl,
    marginBottom: THEME.spacing.xs,
    marginLeft: THEME.spacing.xs,
  },
  card: {
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.lg,
    borderWidth: CARD_BORDER_WIDTH,
    padding: THEME.spacing.xl,
  },
  badge: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    marginBottom: THEME.spacing.md,
  },
  badgeText: {
    letterSpacing: BADGE_LETTER_SPACING,
  },
  title: {
    marginBottom: THEME.spacing.sm,
  },
  description: {
    marginBottom: THEME.spacing.md,
    lineHeight: DESCRIPTION_LINE_HEIGHT,
  },
  price: {
    fontSize: PRICE_FONT_SIZE,
    marginBottom: THEME.spacing.xl,
  },
  button: {
    borderRadius: THEME.radius.pill,
    minHeight: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  buttonText: {
    fontFamily: FONTS.bodyMedium,
    fontSize: BUTTON_FONT_SIZE,
    color: THEME.colors.bg,
  },
});
