/**
 * usePurchaseFlow — single source of truth for entitlement fetching +
 * Pro subscription / cancel actions.
 *
 * Used by both `subscription.tsx` and `PaywallModal.tsx` so duplicated
 * purchase logic and state stays in one place.
 *
 * Pro subscriptions use the `Linking.openURL` redirect flow. Cancel
 * confirmation is driven by `isCancelSheetOpen` / `openCancelSheet` /
 * `confirmCancel` / `dismissCancelSheet`; the consumer screen renders
 * `<CancelSubscriptionSheet>` wired to that state.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Linking } from "react-native";

import {
  cancelSubscription,
  createSubscription,
  fetchEntitlement,
  SUBSCRIPTION_STATUS_ALREADY_SUBSCRIBED,
  type EntitlementState,
} from "../entitlement";
import { parseApiError } from "../errors";
import { showToast } from "../toast";

/** Sentinel `purchasingId` used while the pro subscribe call is in flight. */
export const PURCHASING_PREMIUM_ID = "__premium__";

const ERROR_LOAD_ENTITLEMENT =
  "We couldn't load your subscription info. Try again.";
const WARNING_SUBSCRIPTION_UNAVAILABLE =
  "Subscription is not available at this time.";
const INFO_ALREADY_SUBSCRIBED = "You\u2019re already subscribed.";

export interface UsePurchaseFlowReturn {
  entitlement: EntitlementState | null;
  isLoading: boolean;
  error: string | null;
  /**
   * `PURCHASING_PREMIUM_ID` while the subscribe call is in flight,
   * or `null` when no purchase is active.
   */
  purchasingId: string | null;
  isCancelling: boolean;
  /** True while the confirm-cancel bottom sheet is visible. */
  isCancelSheetOpen: boolean;
  refresh: () => Promise<void>;
  subscribe: () => Promise<void>;
  /** Open the confirm-cancel bottom sheet (no API call yet). */
  openCancelSheet: () => void;
  /** Dismiss the sheet without cancelling. */
  dismissCancelSheet: () => void;
  /** Fire the cancel API call + close the sheet. */
  confirmCancel: () => Promise<void>;
}

interface UsePurchaseFlowOptions {
  /** Auto-load entitlement on mount. Default true. */
  autoLoad?: boolean;
  /**
   * Fires after a new Pro subscription with the latest entitlement state.
   * Does NOT fire for `already_subscribed` responses or cancels — those
   * callers shouldn't show "Purchase complete!" UX.
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
  const [isCancelSheetOpen, setIsCancelSheetOpen] = useState(false);

  // Ref mirror of `entitlement` so `refresh` can read the current value
  // without becoming part of its dependency list (callers like PaywallModal
  // pass `refresh` to a `useEffect` — a changing identity would loop).
  const entitlementRef = useRef<EntitlementState | null>(null);
  useEffect(() => {
    entitlementRef.current = entitlement;
  }, [entitlement]);

  // ---------------------------------------------------------------------
  // Refetch — internal helper used by post-action reloads (success path).
  // Returns the updated state; throws on failure.
  // ---------------------------------------------------------------------
  const refetch = useCallback(async () => {
    const updated = await fetchEntitlement();
    setEntitlement(updated);
    return updated;
  }, []);

  // Public `refresh` — fetches latest entitlement state. Toggles
  // `isLoading` (skeleton) only when there's no current data;
  // surfaces errors as page-level `error` on first load and as a
  // toast on subsequent refreshes.
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
  // Subscribe to Pro
  // ---------------------------------------------------------------------
  const subscribe = useCallback(async () => {
    setPurchasingId(PURCHASING_PREMIUM_ID);
    try {
      const response = await createSubscription();

      if (response.status === SUBSCRIPTION_STATUS_ALREADY_SUBSCRIBED) {
        await refetch();
        showToast({ kind: "info", message: INFO_ALREADY_SUBSCRIBED });
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
      // Backend now raises HTTP 409 ALREADY_SUBSCRIBED instead of a success
      // payload; treat that as the same already-subscribed path.
      if (
        appError.kind === "business" &&
        appError.errorCode === "ALREADY_SUBSCRIBED"
      ) {
        await refetch();
        showToast({ kind: "info", message: INFO_ALREADY_SUBSCRIBED });
        return;
      }
      showToast({ kind: "error", message: appError.message });
    } finally {
      setPurchasingId(null);
    }
  }, [refetch, onPurchaseComplete]);

  // ---------------------------------------------------------------------
  // Cancel subscription — sheet-driven confirmation.
  // ---------------------------------------------------------------------
  const openCancelSheet = useCallback(() => {
    setIsCancelSheetOpen(true);
  }, []);

  const dismissCancelSheet = useCallback(() => {
    setIsCancelSheetOpen(false);
  }, []);

  const confirmCancel = useCallback(async () => {
    setIsCancelling(true);
    try {
      const resp = await cancelSubscription();
      await refetch();
      setIsCancelSheetOpen(false);
      showToast({ kind: "success", message: resp.message });
    } catch (err) {
      const appError = parseApiError(err);
      showToast({ kind: "error", message: appError.message });
    } finally {
      setIsCancelling(false);
    }
  }, [refetch]);

  return {
    entitlement,
    isLoading,
    error,
    purchasingId,
    isCancelling,
    isCancelSheetOpen,
    refresh,
    subscribe,
    openCancelSheet,
    dismissCancelSheet,
    confirmCancel,
  };
}
