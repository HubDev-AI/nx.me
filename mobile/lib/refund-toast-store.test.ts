/**
 * refund-toast-store — module-level dedup of refund toasts. Mirrors the
 * dismissed-jobs-store contract since both wrap a persisted Set the
 * same way.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  REFUND_TOAST_SEEN_MAX_ENTRIES,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../constants/config";
import {
  __resetRefundToastSeenForTests,
  hasSeenRefundToastSync,
  loadRefundToastSeen,
  markRefundToastSeen,
} from "./refund-toast-store";

jest.mock("@react-native-async-storage/async-storage", () => {
  const store = new Map<string, string>();
  return {
    __esModule: true,
    default: {
      getItem: jest.fn(async (key: string) => store.get(key) ?? null),
      setItem: jest.fn(async (key: string, value: string) => {
        store.set(key, value);
      }),
      removeItem: jest.fn(async (key: string) => {
        store.delete(key);
      }),
      clear: jest.fn(async () => {
        store.clear();
      }),
      __getStore: () => store,
    },
  };
});

const mockedStorage = AsyncStorage as unknown as {
  __getStore: () => Map<string, string>;
};

describe("refund-toast-store", () => {
  beforeEach(() => {
    __resetRefundToastSeenForTests();
    mockedStorage.__getStore().clear();
  });

  it("starts empty when storage has no key", async () => {
    const set = await loadRefundToastSeen();
    expect(set.size).toBe(0);
    expect(hasSeenRefundToastSync("job-1")).toBe(false);
  });

  it("hydrates from a previously persisted JSON array", async () => {
    mockedStorage
      .__getStore()
      .set(REFUND_TOAST_SEEN_STORAGE_KEY, JSON.stringify(["a", "b"]));
    const set = await loadRefundToastSeen();
    expect(set.size).toBe(2);
    expect(hasSeenRefundToastSync("a")).toBe(true);
  });

  it("markRefundToastSeen persists to AsyncStorage", async () => {
    await loadRefundToastSeen();
    await markRefundToastSeen("job-1");
    const stored = mockedStorage
      .__getStore()
      .get(REFUND_TOAST_SEEN_STORAGE_KEY);
    expect(stored).toBeDefined();
    expect(JSON.parse(stored!)).toEqual(["job-1"]);
  });

  it("hasSeenRefundToastSync reflects markings without re-hydrating", async () => {
    await loadRefundToastSeen();
    await markRefundToastSeen("job-x");
    expect(hasSeenRefundToastSync("job-x")).toBe(true);
  });

  it("idempotent: marking the same id twice keeps a single entry", async () => {
    await loadRefundToastSeen();
    await markRefundToastSeen("job-1");
    await markRefundToastSeen("job-1");
    const stored = mockedStorage
      .__getStore()
      .get(REFUND_TOAST_SEEN_STORAGE_KEY);
    expect(JSON.parse(stored!)).toEqual(["job-1"]);
  });

  it("respects REFUND_TOAST_SEEN_MAX_ENTRIES cap", async () => {
    await loadRefundToastSeen();
    for (let i = 0; i < REFUND_TOAST_SEEN_MAX_ENTRIES + 5; i++) {
      await markRefundToastSeen(`job-${i}`);
    }
    const stored = mockedStorage
      .__getStore()
      .get(REFUND_TOAST_SEEN_STORAGE_KEY);
    const parsed = JSON.parse(stored!) as string[];
    expect(parsed.length).toBe(REFUND_TOAST_SEEN_MAX_ENTRIES);
    // Oldest entries dropped first; newest preserved.
    expect(parsed[parsed.length - 1]).toBe(
      `job-${REFUND_TOAST_SEEN_MAX_ENTRIES + 4}`,
    );
    expect(parsed[0]).toBe("job-5");
  });

  it("ignores corrupt JSON in storage and starts empty", async () => {
    mockedStorage.__getStore().set(REFUND_TOAST_SEEN_STORAGE_KEY, "{bad");
    const set = await loadRefundToastSeen();
    expect(set.size).toBe(0);
  });
});
