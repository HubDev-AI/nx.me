/**
 * Dismissed-errored-jobs store.
 *
 * Persisted set of job_ids the user has explicitly removed from the
 * profile grid via long-press → "Remove from profile". The server still
 * has the row (audit trail + refund history); we just suppress it
 * client-side on the next /history refetch.
 *
 * Device-scoped by design — the server has no concept of a "dismissed"
 * cell, so the same job can re-appear on another device. That's
 * acceptable because the credit refund is the durable artifact; the
 * cell is a UI affordance.
 *
 * Backed by the shared persistent-set-store so the hydrate/add/trim/
 * clear mechanics stay in one place. `clearDismissedJobs` is called
 * exclusively by the delete-account flow via `wipeLocalDeviceState`;
 * logout stays narrow (tokens only).
 */
import { PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY } from "../constants/config";

import { createPersistentSetStore } from "./persistent-set-store";

/**
 * Hard cap on persisted ids — stops the set growing unboundedly if a
 * user dismisses thousands of failures over the app's lifetime. 500
 * covers years of normal-cadence use; oldest entries fall off first
 * via insertion order.
 */
const DISMISSED_JOBS_MAX_ENTRIES = 500;

const store = createPersistentSetStore({
  storageKey: PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
  maxEntries: DISMISSED_JOBS_MAX_ENTRIES,
  clearErrorLogLabel: "clearDismissedJobs",
});

export async function loadDismissedJobIds(): Promise<Set<string>> {
  return store.load();
}

export async function addDismissedJobId(jobId: string): Promise<void> {
  return store.add(jobId);
}

export function getDismissedJobIdsSync(): ReadonlySet<string> {
  return store.getSync();
}

export async function clearDismissedJobs(): Promise<void> {
  return store.clear();
}

export function __resetDismissedJobIdsForTests(): void {
  store.__resetForTests();
}
