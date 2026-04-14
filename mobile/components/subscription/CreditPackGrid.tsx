/**
 * CreditPackGrid — list of credit pack options on the subscription screen.
 *
 * Reuses the paywall `CreditPackCard` so subscription and paywall stay
 * visually consistent (single source of truth for the card layout).
 */
import { StyleSheet, View } from "react-native";

import { THEME } from "../../constants/theme";
import { Caption, Label } from "../ui/Text";
import { CreditPackCard } from "../paywall/CreditPackCard";
import type { CreditPackOption } from "../../lib/entitlement";

interface CreditPackGridProps {
  packs: CreditPackOption[];
  /** `pack_id` of the pack currently being purchased, or null. */
  purchasingId: string | null;
  onBuy: (pack: CreditPackOption) => void;
}

export function CreditPackGrid({
  packs,
  purchasingId,
  onBuy,
}: CreditPackGridProps) {
  if (packs.length === 0) return null;

  const isPurchasing = purchasingId !== null;

  return (
    <>
      <Label style={styles.sectionLabel} maxFontSizeMultiplier={1.3}>
        CREDIT PACKS
      </Label>
      <Caption color="muted" style={styles.sectionDescription}>
        Buy credits to unlock individual analyses
      </Caption>
      <View style={styles.list}>
        {packs.map((pack) => (
          <CreditPackCard
            key={pack.pack_id}
            pack={pack}
            onPurchase={onBuy}
            isLoading={purchasingId === pack.pack_id}
            disabled={isPurchasing && purchasingId !== pack.pack_id}
          />
        ))}
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
