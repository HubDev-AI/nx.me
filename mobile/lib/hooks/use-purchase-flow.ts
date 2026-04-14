/**
 * usePurchaseFlow — single source of truth for entitlement fetching +
 * credit pack / premium / cancel actions.
 *
 * Used by both `subscription.tsx` and `PaywallModal.tsx` so duplicated
 * purchase logic and state stays in one place.
 *
 * The hook keeps `Linking.openURL` for the Stripe Checkout fallback
 * (PR6 will swap this for the in-app Stripe Payment Sheet) and the
 * native `Alert.alert` for the cancel confirmation (PR4 will swap this
 * for the custom bottom sheet).
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Linking } from "react-native";

import {
  cancelSubscription,
  createSubscription,
  fetchEntitlement,
  purchaseCredits,
  SUBSCRIPTION_STATUS_ALREADY_SUBSCRIBED,
  type CreditPackOption,
  type EntitlementState,
} from "../entitlement";
import { parseApiError } from "../errors";
import { showToast } from "../toast";

/** Sentinel `purchasingId` used while the premium subscribe call is in flight. */
export const PURCHASING_PREMIUM_ID = "__premium__";

const ERROR_LOAD_ENTITLEMENT =
  "We couldn't load your subscription info. Try again.";
const WARNING_SUBSCRIPTION_UNAVAILABLE =
  "Subscription is not available at this time.";

const CANCEL_TITLE = "Cancel Subscription";
const CANCEL_MESSAGE =
  "Your premium benefits will remain until the end of your billing period.";
const CANCEL_KEEP_LABEL = "Keep Subscription";
const CANCEL_CONFIRM_LABEL = "Cancel";

export interface UsePurchaseFlowReturn {
  entitlement: EntitlementState | null;
  isLoading: boolean;
  error: string | null;
  /**
   * `pack_id` of the credit pack currently being purchased,
   * `PURCHASING_PREMIUM_ID` while the subscribe call is in flight,
   * or `null` when no purchase is active.
   */
  purchasingId: string | null;
  isCancelling: boolean;
  refresh: () => Promise<void>;
  buyCredits: (pack: CreditPackOption) => Promise<void>;
  subscribe: () => Promise<void>;
  cancel: () => void;
}

interface UsePurchaseFlowOptions {
  /** Auto-load entitlement on mount. Default true. */
  autoLoad?: boolean;
  /**
   * Fires after a successful credit pack purchase or new premium
   * subscription with the latest entitlement state. Does NOT fire
   * for `already_subscribed` responses or cancels — those callers
   * shouldn't show "Purchase complete!" UX.
   */
  onPurchaseComplete?: (state: EntitlementState) => void;
}

export function usePurchaseFlow({
  autoLoad = true,
  onPurchaseComplete,
}: UsePurchaseFlowOptions = {}): UsePurchaseFlowReturn {
  const [entitlement, setEntitlement] = useState<EntitlementState | null>(null);
  const [isLoading, setIsLoading] = useState(autoLoad);
  const [error, setError] = useState<string | null>(null);
  const [purchasingId, setPurchasingId] = useState<string | null>(null);
  const [isCancelling, setIsCancelling] = useState(false);

  // Ref mirror of `entitlement` so `refresh` can read the current value
  // without becoming part of its dependency list (callers like PaywallModal
  // pass `refresh` to a `useEffect` — a changing identity would loop).
  const entitlementRef = useRef<EntitlementState | null>(null);
  useEffect(() => {
    entitlementRef.current = entitlement;
  }, [entitlement]);

  // ---------------------------------------------------------------------
  // Refetch — internal helper used by post-action reloads (success path).
  // Returns the updated state; throws on failure (caller decides how to
  // surface it — usually via toast since the user already has data).
  // ---------------------------------------------------------------------
  const refetch = useCallback(async () => {
    const updated = await fetchEntitlement();
    setEntitlement(updated);
    return updated;
  }, []);

  // Public `refresh` — fetches latest entitlement state. Toggles
  // `isLoading` (skeleton) only when there's no current data;
  // surfaces errors as page-level `error` on first load and as a
  // toast on subsequent refreshes. Used for mount, retry, and
  // pull-to-refresh. Stable identity so callers can put it in
  // `useEffect` deps without looping.
  const refresh = useCallback(async () => {
    const hadData = entitlementRef.current !== null;
    if (!hadData) setIsLoading(true);
    try {
      await refetch();
      setError(null);
    } catch (err) {
      if (hadData) {
        const appError = parseApiError(err);
        showToast({ kind: "error", message: appError.message });
      } else {
        setError(ERROR_LOAD_ENTITLEMENT);
      }
    } finally {
      if (!hadData) setIsLoading(false);
    }
  }, [refetch]);

  useEffect(() => {
    if (autoLoad) {
      refresh();
    }
  }, [autoLoad, refresh]);

  // ---------------------------------------------------------------------
  // Buy credits
  // ---------------------------------------------------------------------
  const buyCredits = useCallback(
    async (pack: CreditPackOption) => {
      setPurchasingId(pack.pack_id);
      try {
        const { checkout_url } = await purchaseCredits(pack.pack_id);
        await Linking.openURL(checkout_url);
        const updated = await refetch();
        onPurchaseComplete?.(updated);
      } catch (err) {
        const appError = parseApiError(err);
        showToast({ kind: "error", message: appError.message });
      } finally {
        setPurchasingId(null);
      }
    },
    [refetch, onPurchaseComplete],
  );

  // ---------------------------------------------------------------------
  // Subscribe to premium
  // ---------------------------------------------------------------------
  const subscribe = useCallback(async () => {
    setPurchasingId(PURCHASING_PREMIUM_ID);
    try {
      const response = await createSubscription();

      if (response.status === SUBSCRIPTION_STATUS_ALREADY_SUBSCRIBED) {
        // Not a new purchase — silently re-sync state without firing
        // `onPurchaseComplete` (which would show a misleading "Purchase
        // complete!" banner in the paywall modal).
        await refetch();
        return;
      }

      if (!response.checkout_url) {
        showToast({ kind: "warning", message: WARNING_SUBSCRIPTION_UNAVAILABLE });
        return;
      }

      await Linking.openURL(response.checkout_url);
      const updated = await refetch();
      onPurchaseComplete?.(updated);
    } catch (err) {
      const appError = parseApiError(err);
      showToast({ kind: "error", message: appError.message });
    } finally {
      setPurchasingId(null);
    }
  }, [refetch, onPurchaseComplete]);

  // ---------------------------------------------------------------------
  // Cancel subscription (PR4 will replace the native Alert with a sheet)
  // ---------------------------------------------------------------------
  const cancel = useCallback(() => {
    Alert.alert(CANCEL_TITLE, CANCEL_MESSAGE, [
      { text: CANCEL_KEEP_LABEL, style: "cancel" },
      {
        text: CANCEL_CONFIRM_LABEL,
        style: "destructive",
        onPress: async () => {
          setIsCancelling(true);
          try {
            const resp = await cancelSubscription();
            await refetch();
            showToast({ kind: "success", message: resp.message });
          } catch (err) {
            const appError = parseApiError(err);
            showToast({ kind: "error", message: appError.message });
          } finally {
            setIsCancelling(false);
          }
        },
      },
    ]);
  }, [refetch]);

  return {
    entitlement,
    isLoading,
    error,
    purchasingId,
    isCancelling,
    refresh,
    buyCredits,
    subscribe,
    cancel,
  };
}
