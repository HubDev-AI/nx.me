/**
 * CreditPackGrid — credit pack option on the subscription screen.
 *
 * The credits-only payments rebuild (Unit 12) uses a single pack option
 * (not an array), so this component wraps a single `CreditPackCard`.
 * Reuses the paywall `CreditPackCard` so subscription and paywall stay
 * visually consistent (single source of truth for the card layout).
 */
import { StyleSheet, View } from "react-native";

import { THEME } from "../../constants/theme";
import { Caption, Label } from "../ui/Text";
import { CreditPackCard } from "../paywall/CreditPackCard";
import type { PackOption } from "../../lib/entitlement";

interface CreditPackGridProps {
  pack: PackOption;
  /** `price_id` of the pack currently being purchased, or null. */
  purchasingId: string | null;
  onBuy: (pack: PackOption) => void;
}

export function CreditPackGrid({
  pack,
  purchasingId,
  onBuy,
}: CreditPackGridProps) {
  const isPurchasing = purchasingId !== null;

  return (
    <>
      <Label style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
        CREDIT PACK
      </Label>
      <Caption color="muted" style={styles.sectionDescription}>
        Buy credits to unlock individual glow-ups
      </Caption>
      <View style={styles.list}>
        <CreditPackCard
          pack={pack}
          onPurchase={onBuy}
          isLoading={purchasingId === pack.price_id}
          disabled={isPurchasing && purchasingId !== pack.price_id}
        />
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  sectionLabel: {
    marginTop: THEME.spacing.xxl,
    marginBottom: THEME.spacing.xs,
    marginLeft: THEME.spacing.xs,
  },
  sectionDescription: {
    marginBottom: THEME.spacing.md,
    marginLeft: THEME.spacing.xs,
  },
  list: {
    gap: THEME.spacing.md,
  },
});
