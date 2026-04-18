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
 * Singleton in-memory mirror is kept in sync with the AsyncStorage write
 * so callers can do synchronous filtering on the hot path (rendering
 * the grid) without awaiting storage.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import { PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY } from "../constants/config";

/**
 * Hard cap on persisted ids — stops the set growing unboundedly if a
 * user dismisses thousands of failures over the app's lifetime. 500
 * covers years of normal-cadence use; oldest entries fall off first
 * via insertion order.
 */
const DISMISSED_JOBS_MAX_ENTRIES = 500;

let cache: Set<string> | null = null;
let hydratePromise: Promise<Set<string>> | null = null;

/**
 * Load the persisted dismiss set into the in-memory cache. Subsequent
 * calls return the cached set — only the first call hits AsyncStorage.
 * Safe to call multiple times concurrently; the underlying read is
 * deduped via `hydratePromise`.
 */
export async function loadDismissedJobIds(): Promise<Set<string>> {
  if (cache !== null) return cache;
  if (hydratePromise !== null) return hydratePromise;

  hydratePromise = (async () => {
    try {
      const raw = await AsyncStorage.getItem(
        PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
      );
      if (raw) {
        const parsed = JSON.parse(raw) as unknown;
        if (Array.isArray(parsed)) {
          cache = new Set(
            parsed.filter((entry): entry is string => typeof entry === "string"),
          );
          return cache;
        }
      }
    } catch {
      // Corrupt JSON or storage failure — fall through to an empty
      // set. The user will see the cells re-appear; safer than
      // throwing on a hot path.
    }
    cache = new Set();
    return cache;
  })();

  const result = await hydratePromise;
  hydratePromise = null;
  return result;
}

/**
 * Synchronous accessor used during render. Returns the cached set if
 * hydrated; otherwise returns an empty set so the grid renders without
 * blocking. The async hydrate runs in the background and a re-render
 * picks up the populated set on next tick.
 */
export function getDismissedJobIdsSync(): ReadonlySet<string> {
  return cache ?? new Set();
}

/**
 * Mark a job as dismissed. Updates the in-memory cache synchronously
 * so a subsequent render reflects the change immediately, then
 * fire-and-forget the AsyncStorage write — failure is logged-and-swallowed,
 * the worst case is the cell re-appears on the next launch.
 */
export async function addDismissedJobId(jobId: string): Promise<void> {
  if (cache === null) {
    await loadDismissedJobIds();
  }
  if (cache!.has(jobId)) return;

  cache!.add(jobId);

  // Trim oldest entries when over the cap. Set preserves insertion
  // order, so we can drop from the front via array conversion.
  if (cache!.size > DISMISSED_JOBS_MAX_ENTRIES) {
    const arr = Array.from(cache!);
    cache = new Set(arr.slice(arr.length - DISMISSED_JOBS_MAX_ENTRIES));
  }

  try {
    await AsyncStorage.setItem(
      PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
      JSON.stringify(Array.from(cache!)),
    );
  } catch {
    // Persisting is best-effort; the in-memory set still suppresses
    // the cell for the rest of the session.
  }
}

/**
 * Reset the dismissed-jobs store for a full device wipe. Clears the
 * in-memory cache, the in-flight hydrate promise, and the backing
 * AsyncStorage key. Storage errors are swallowed — the in-memory
 * reset is the durable signal.
 *
 * Called exclusively by the delete-account flow via
 * `wipeLocalDeviceState`. Logout stays narrow (tokens only).
 */
export async function clearDismissedJobs(): Promise<void> {
  cache = new Set();
  hydratePromise = null;
  try {
    await AsyncStorage.removeItem(PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY);
  } catch (err) {
    if (__DEV__) console.warn("clearDismissedJobs: storage remove failed", err);
  }
}

/**
 * Test seam — resets module state. Production code should never need
 * to call this.
 */
export function __resetDismissedJobIdsForTests(): void {
  cache = null;
  hydratePromise = null;
}
