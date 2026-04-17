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
import { useEffect } from "react";

import {
  REFUND_TOAST_CANCELLED,
  REFUND_TOAST_FAILED,
} from "../../constants/config";
import type { JobResult } from "../analysis";
import { showToast } from "../toast";
import {
  hasSeenRefundToastSync,
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

  // Hydrate the persisted set once on mount so the very first
  // refunded-job poll can see it. Without this, the first poll
  // after launch would always fire the toast.
  useEffect(() => {
    void loadRefundToastSeen();
  }, []);

  useEffect(() => {
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
  }, [result, pathname]);
}
