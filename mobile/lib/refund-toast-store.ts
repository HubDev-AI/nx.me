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
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  REFUND_TOAST_SEEN_MAX_ENTRIES,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../constants/config";

let cache: Set<string> | null = null;
let hydratePromise: Promise<Set<string>> | null = null;

/**
 * Hydrate the persisted seen-set into the in-memory cache. Subsequent
 * calls return the cached set; only the first call hits AsyncStorage.
 * Concurrent calls share the same in-flight promise.
 */
export async function loadRefundToastSeen(): Promise<Set<string>> {
  if (cache !== null) return cache;
  if (hydratePromise !== null) return hydratePromise;

  hydratePromise = (async () => {
    try {
      const raw = await AsyncStorage.getItem(REFUND_TOAST_SEEN_STORAGE_KEY);
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
      // set. Worst case the toast re-fires once on the next failure.
    }
    cache = new Set();
    return cache;
  })();

  const result = await hydratePromise;
  hydratePromise = null;
  return result;
}

/**
 * Synchronous accessor for the in-memory cache. Returns false if not
 * yet hydrated — callers should pair with a fire-and-forget
 * `loadRefundToastSeen()` on mount so the cache is populated by the
 * time a poll resolves.
 */
export function hasSeenRefundToastSync(jobId: string): boolean {
  return cache?.has(jobId) ?? false;
}

/**
 * Whether the persisted seen-set has been read into memory. Callers
 * that need to make a "show or skip the toast" decision must defer
 * until this returns true — otherwise a cold-start poll that resolves
 * before AsyncStorage finishes can re-fire a toast for a job already
 * seen on a previous launch.
 */
export function isRefundToastStoreHydrated(): boolean {
  return cache !== null;
}

/**
 * Record that a job's refund toast has fired. Updates the in-memory
 * cache synchronously so a follow-up poll in the same session can't
 * double-fire, then fire-and-forget the AsyncStorage write.
 */
export async function markRefundToastSeen(jobId: string): Promise<void> {
  if (cache === null) {
    await loadRefundToastSeen();
  }
  if (cache!.has(jobId)) return;

  cache!.add(jobId);

  if (cache!.size > REFUND_TOAST_SEEN_MAX_ENTRIES) {
    const arr = Array.from(cache!);
    cache = new Set(arr.slice(arr.length - REFUND_TOAST_SEEN_MAX_ENTRIES));
  }

  try {
    await AsyncStorage.setItem(
      REFUND_TOAST_SEEN_STORAGE_KEY,
      JSON.stringify(Array.from(cache!)),
    );
  } catch {
    // Persistence is best-effort. The in-memory set still dedups
    // for the rest of the session; on next launch the toast may
    // re-fire once before the next markSeen succeeds.
  }
}

/** Test seam — production code should never call this. */
export function __resetRefundToastSeenForTests(): void {
  cache = null;
  hydratePromise = null;
}
