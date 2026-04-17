/**
 * useRefundToast — fires a one-time success toast when a job's
 * `credit_refunded` flag flips true.
 *
 * Two surfaces observe the same job:
 *  1. Result screen poller (mobile/app/result/[jobId].tsx)
 *  2. Profile pending-cell poller (mobile/components/profile/PendingGlowUpCell.tsx)
 *
 * Both call this hook with the latest JobResult. Module-level dedup
 * (refund-toast-store) ensures the toast fires exactly once per job
 * across the device's lifetime — even after a kill+relaunch.
 *
 * Suppression rules:
 *  - `credit_refunded !== true` → no-op (most polls).
 *  - On `/(auth)` routes → toast is suppressed but the jobId is
 *    still marked seen, so a later non-auth screen doesn't replay
 *    the banner.
 */
import { usePathname } from "expo-router";
import { useEffect, useState } from "react";

import {
  REFUND_TOAST_CANCELLED,
  REFUND_TOAST_FAILED,
} from "../../constants/config";
import type { JobResult } from "../analysis";
import { showToast } from "../toast";
import {
  hasSeenRefundToastSync,
  isRefundToastStoreHydrated,
  loadRefundToastSeen,
  markRefundToastSeen,
} from "../refund-toast-store";

/** Auth-route prefix used by `/(auth)/login`, `/(auth)/register`, etc. */
const AUTH_ROUTE_PREFIX = "/(auth)";

function copyForStatus(status: string): string {
  if (status === "cancelled") return REFUND_TOAST_CANCELLED;
  return REFUND_TOAST_FAILED;
}

/**
 * Observe the latest job-status poll result and fire the refund
 * toast at most once per device per job_id. Safe to call from
 * multiple components observing the same job — the underlying store
 * dedups across observers and across launches.
 */
export function useRefundToast(result: JobResult | undefined): void {
  const pathname = usePathname();
  // Track hydration so we don't fire a toast against an empty cache
  // during the cold-start window. `hasSeenRefundToastSync` returns
  // false before the persisted set has been read in — without this
  // gate, a poll that resolves before AsyncStorage finishes would
  // re-fire a toast for a job already seen on a prior launch.
  const [hydrated, setHydrated] = useState<boolean>(
    isRefundToastStoreHydrated(),
  );

  useEffect(() => {
    if (hydrated) return;
    let cancelled = false;
    void loadRefundToastSeen().then(() => {
      if (!cancelled) setHydrated(true);
    });
    return () => {
      cancelled = true;
    };
  }, [hydrated]);

  useEffect(() => {
    if (!hydrated) return;
    if (!result) return;
    if (result.credit_refunded !== true) return;
    if (hasSeenRefundToastSync(result.job_id)) return;

    // Mark first — synchronous Set mutation prevents a second poll
    // in the same session from squeezing through. AsyncStorage write
    // is fire-and-forget; failure leaves the in-memory dedup intact.
    void markRefundToastSeen(result.job_id);

    // Auth-screen suppression: the user is mid-login; a banner
    // overlapping inputs would be disruptive. The seen marker
    // is already set so a later non-auth screen won't re-fire.
    if (pathname.startsWith(AUTH_ROUTE_PREFIX)) return;

    showToast({
      kind: "success",
      message: copyForStatus(result.status),
    });
  }, [hydrated, result, pathname]);
}
