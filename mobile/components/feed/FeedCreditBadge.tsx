/**
 * FeedCreditBadge — entitlement-aware credit badge for the feed header.
 *
 * Fetches the user's entitlement on mount and displays remaining
 * trials or credits. Tapping navigates to /subscription.
 *
 * Shows nothing while loading or if the user is not authenticated,
 * so it's safe to render unconditionally.
 */
import { useEffect, useState, useCallback } from "react";
import { Pressable } from "react-native";
import { useRouter } from "expo-router";

import { CreditBadge } from "../paywall/CreditBadge";
import { fetchEntitlement, type EntitlementState } from "../../lib/entitlement";
import { useAuth } from "../../lib/auth-context";

export function FeedCreditBadge() {
  const router = useRouter();
  // Entitlement endpoint accepts JWT or guest token — show badge for both.
  const { session } = useAuth();
  const hasSession = !session.isAnon;
  const [entitlement, setEntitlement] = useState<EntitlementState | null>(null);

  useEffect(() => {
    if (!hasSession) return;

    let cancelled = false;

    async function load() {
      try {
        const data = await fetchEntitlement();
        if (!cancelled) setEntitlement(data);
      } catch {
        // Silently fail — badge just won't show
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [hasSession]);

  const handlePress = useCallback(() => {
    router.push("/subscription");
  }, [router]);

  // Don't render anything if not authenticated or data not loaded
  if (!hasSession || !entitlement) return null;

  // Determine which count to display:
  // - If user has trial analyses remaining, show that
  // - Otherwise show credit balance
  const displayCount =
    entitlement.trial_analyses_remaining > 0
      ? entitlement.trial_analyses_remaining
      : entitlement.credit_balance;

  return (
    <Pressable
      onPress={handlePress}
      accessibilityLabel={`${displayCount} credits remaining. Tap to manage subscription.`}
      accessibilityRole="button"
    >
      <CreditBadge balance={displayCount} size="small" />
    </Pressable>
  );
}
