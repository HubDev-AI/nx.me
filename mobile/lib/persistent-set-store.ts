/**
 * Shared factory for persisted string-set stores.
 *
 * Two on-device stores — dismissed errored jobs and seen refund toasts —
 * share the exact same shape:
 *   - Singleton in-memory Set mirror of an AsyncStorage-backed JSON array.
 *   - Hydrate-once with in-flight dedup so concurrent callers share a read.
 *   - Sync accessor that returns safe defaults when not yet hydrated.
 *   - Capped insertion-order trim so the persisted array never grows
 *     unboundedly over the app's lifetime.
 *   - `clear()` used by the delete-account flow; storage errors are
 *     swallowed — the in-memory reset is the durable signal.
 *
 * This module owns the mechanics; each consumer exports the thin named
 * functions its callers (and jest.spyOn) depend on.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

export interface PersistentSetStore {
  /** Hydrate the persisted set into cache; concurrent calls dedup. */
  load(): Promise<Set<string>>;
  /** Mark a value as present. Updates cache first, then persists. */
  add(value: string): Promise<void>;
  /** Synchronous membership check; false when not yet hydrated. */
  hasSync(value: string): boolean;
  /** Synchronous snapshot of the cache; empty set when not yet hydrated. */
  getSync(): ReadonlySet<string>;
  /** True once `load()` has populated the cache. */
  isHydrated(): boolean;
  /** Reset the cache and remove the persisted key. Storage errors swallowed. */
  clear(): Promise<void>;
  /** Test seam — resets module-scoped state. */
  __resetForTests(): void;
}

export interface PersistentSetStoreOptions {
  /** AsyncStorage key backing this set. */
  storageKey: string;
  /** Hard cap on persisted entries — oldest fall off first. */
  maxEntries: number;
  /** Label used in the `clear()` warning log so misrouted errors are traceable. */
  clearErrorLogLabel: string;
}

export function createPersistentSetStore(
  opts: PersistentSetStoreOptions,
): PersistentSetStore {
  let cache: Set<string> | null = null;
  let hydratePromise: Promise<Set<string>> | null = null;

  async function load(): Promise<Set<string>> {
    if (cache !== null) return cache;
    if (hydratePromise !== null) return hydratePromise;

    hydratePromise = (async () => {
      try {
        const raw = await AsyncStorage.getItem(opts.storageKey);
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
        // Corrupt JSON or storage failure — fall through to empty set.
      }
      cache = new Set();
      return cache;
    })();

    const result = await hydratePromise;
    hydratePromise = null;
    return result;
  }

  async function add(value: string): Promise<void> {
    if (cache === null) {
      await load();
    }
    if (cache!.has(value)) return;

    cache!.add(value);

    // Set preserves insertion order; trim the oldest from the front.
    if (cache!.size > opts.maxEntries) {
      const arr = Array.from(cache!);
      cache = new Set(arr.slice(arr.length - opts.maxEntries));
    }

    try {
      await AsyncStorage.setItem(
        opts.storageKey,
        JSON.stringify(Array.from(cache!)),
      );
    } catch {
      // Persistence is best-effort — the in-memory set still dedups
      // for the rest of the session.
    }
  }

  function hasSync(value: string): boolean {
    return cache?.has(value) ?? false;
  }

  function getSync(): ReadonlySet<string> {
    return cache ?? new Set();
  }

  function isHydrated(): boolean {
    return cache !== null;
  }

  async function clear(): Promise<void> {
    cache = new Set();
    hydratePromise = null;
    try {
      await AsyncStorage.removeItem(opts.storageKey);
    } catch (err) {
      if (__DEV__) {
        console.warn(`${opts.clearErrorLogLabel}: storage remove failed`, err);
      }
    }
  }

  function __resetForTests(): void {
    cache = null;
    hydratePromise = null;
  }

  return { load, add, hasSync, getSync, isHydrated, clear, __resetForTests };
}
