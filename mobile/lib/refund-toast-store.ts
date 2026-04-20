/**
 * Refund-toast dedup store.
 *
 * Singleton tracking which job_ids have already fired their refund
 * toast on this device. Survives app kill via AsyncStorage so a
 * relaunch doesn't replay the banner.
 *
 * Two writers (the result-screen poller and the profile pending-cell
 * poller) observe the same job. The module-level Set ensures only
 * the first one fires the toast — ordering doesn't matter, the loser
 * sees `hasSeen → true` and bails.
 *
 * The cell rendered on the profile grid carries the durable, cross-
 * device error signal (errored variant). The toast is a transient
 * heads-up — re-firing once per device per job is acceptable because
 * the cell tells the same story persistently.
 *
 * Backed by the shared persistent-set-store. `clearRefundToastSeen` is
 * called exclusively by the delete-account flow via
 * `wipeLocalDeviceState`; logout stays narrow (tokens only).
 */
import {
  REFUND_TOAST_SEEN_MAX_ENTRIES,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../constants/config";

import { createPersistentSetStore } from "./persistent-set-store";

const store = createPersistentSetStore({
  storageKey: REFUND_TOAST_SEEN_STORAGE_KEY,
  maxEntries: REFUND_TOAST_SEEN_MAX_ENTRIES,
  clearErrorLogLabel: "clearRefundToastSeen",
});

export async function loadRefundToastSeen(): Promise<Set<string>> {
  return store.load();
}

export function hasSeenRefundToastSync(jobId: string): boolean {
  return store.hasSync(jobId);
}

/**
 * Whether the persisted seen-set has been read into memory. Callers
 * that need to make a "show or skip the toast" decision must defer
 * until this returns true — otherwise a cold-start poll that resolves
 * before AsyncStorage finishes can re-fire a toast for a job already
 * seen on a previous launch.
 */
export function isRefundToastStoreHydrated(): boolean {
  return store.isHydrated();
}

export async function markRefundToastSeen(jobId: string): Promise<void> {
  return store.add(jobId);
}

export async function clearRefundToastSeen(): Promise<void> {
  return store.clear();
}

export function __resetRefundToastSeenForTests(): void {
  store.__resetForTests();
}
