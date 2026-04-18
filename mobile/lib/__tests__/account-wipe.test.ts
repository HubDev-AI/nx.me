import AsyncStorage from "@react-native-async-storage/async-storage";

import * as secureStorage from "../secure-storage";
import * as dismissedJobs from "../dismissed-jobs-store";
import * as refundToast from "../refund-toast-store";
import { mutationQueue } from "../offline-queue";
import { queryClient } from "../query-client";
import {
  SECURE_STORE_KEYS,
  PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
  REFUND_TOAST_SEEN_STORAGE_KEY,
} from "../../constants/config";
import { wipeLocalDeviceState } from "../account-wipe";

jest.mock("@react-native-async-storage/async-storage", () => ({
  multiRemove: jest.fn().mockResolvedValue(undefined),
  removeItem: jest.fn().mockResolvedValue(undefined),
}));

// `queryClient` pulls in `toast`, which pulls in the native `burnt`
// module. Stub it so the module graph loads in the Jest environment.
jest.mock("burnt", () => ({
  toast: jest.fn(),
  dismissAllAlerts: jest.fn(),
}));

describe("wipeLocalDeviceState", () => {
  beforeEach(() => {
    jest.spyOn(secureStorage, "deleteItem").mockResolvedValue(undefined);
    jest.spyOn(dismissedJobs, "clearDismissedJobs").mockResolvedValue(undefined);
    jest.spyOn(refundToast, "clearRefundToastSeen").mockResolvedValue(undefined);
    jest.spyOn(mutationQueue, "clear").mockReturnValue(undefined);
    jest.spyOn(queryClient, "clear").mockReturnValue(undefined);
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("deletes every SecureStore key", async () => {
    await wipeLocalDeviceState();

    const deleted = (secureStorage.deleteItem as jest.Mock).mock.calls.map(
      (c) => c[0],
    );
    expect(deleted).toEqual(
      expect.arrayContaining(Object.values(SECURE_STORE_KEYS)),
    );
    expect(deleted).toHaveLength(Object.keys(SECURE_STORE_KEYS).length);
  });

  it("clears every AsyncStorage key", async () => {
    await wipeLocalDeviceState();

    expect(AsyncStorage.multiRemove).toHaveBeenCalledWith(
      expect.arrayContaining([
        PROFILE_DISMISSED_ERRORED_JOBS_STORAGE_KEY,
        REFUND_TOAST_SEEN_STORAGE_KEY,
      ]),
    );
  });

  it("resets in-memory singletons and the query cache", async () => {
    await wipeLocalDeviceState();

    expect(dismissedJobs.clearDismissedJobs).toHaveBeenCalledTimes(1);
    expect(refundToast.clearRefundToastSeen).toHaveBeenCalledTimes(1);
    expect(mutationQueue.clear).toHaveBeenCalledTimes(1);
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
  });
});
