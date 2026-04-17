/**
 * dismissed-jobs-store — hydrate from AsyncStorage, persist on add,
 * dedupe in-memory, and trim past the entry cap.
 */
import AsyncStorage from "@react-native-async-storage/async-storage";

import { PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY } from "../constants/config";
import {
  __resetDismissedJobIdsForTests,
  addDismissedJobId,
  getDismissedJobIdsSync,
  loadDismissedJobIds,
} from "./dismissed-jobs-store";

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

describe("dismissed-jobs-store", () => {
  beforeEach(() => {
    __resetDismissedJobIdsForTests();
    mockedStorage.__getStore().clear();
  });

  it("hydrates an empty set when storage is missing the key", async () => {
    const set = await loadDismissedJobIds();
    expect(set.size).toBe(0);
    expect(getDismissedJobIdsSync().size).toBe(0);
  });

  it("hydrates from a previously persisted JSON array", async () => {
    mockedStorage
      .__getStore()
      .set(
        PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
        JSON.stringify(["job-a", "job-b"]),
      );

    const set = await loadDismissedJobIds();
    expect(set.has("job-a")).toBe(true);
    expect(set.has("job-b")).toBe(true);
    expect(set.size).toBe(2);
  });

  it("addDismissedJobId persists to AsyncStorage", async () => {
    await loadDismissedJobIds();
    await addDismissedJobId("job-1");

    const stored = mockedStorage
      .__getStore()
      .get(PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY);
    expect(stored).toBeDefined();
    expect(JSON.parse(stored!)).toEqual(["job-1"]);
  });

  it("getDismissedJobIdsSync reflects adds without re-hydrating", async () => {
    await loadDismissedJobIds();
    await addDismissedJobId("job-x");
    expect(getDismissedJobIdsSync().has("job-x")).toBe(true);
  });

  it("addDismissedJobId is idempotent for the same id", async () => {
    await loadDismissedJobIds();
    await addDismissedJobId("job-1");
    await addDismissedJobId("job-1");

    const stored = mockedStorage
      .__getStore()
      .get(PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY);
    expect(JSON.parse(stored!)).toEqual(["job-1"]);
  });

  it("ignores corrupt JSON in storage and starts empty", async () => {
    mockedStorage
      .__getStore()
      .set(PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY, "{not-json");
    const set = await loadDismissedJobIds();
    expect(set.size).toBe(0);
  });

  it("filters non-string entries in persisted JSON array", async () => {
    mockedStorage
      .__getStore()
      .set(
        PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
        JSON.stringify(["job-a", 42, null, "job-b"]),
      );
    const set = await loadDismissedJobIds();
    expect(set.size).toBe(2);
    expect(set.has("job-a")).toBe(true);
    expect(set.has("job-b")).toBe(true);
  });
});
