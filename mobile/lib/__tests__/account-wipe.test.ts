import * as secureStorage from "../secure-storage";
import * as dismissedJobs from "../dismissed-jobs-store";
import * as refundToast from "../refund-toast-store";
import { mutationQueue } from "../offline-queue";
import { queryClient } from "../query-client";
import { SECURE_STORE_KEYS } from "../../constants/config";
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

  it("swallows per-key SecureStore errors so the remaining keys still clear", async () => {
    const warnSpy = jest.spyOn(console, "warn").mockImplementation(() => {});
    (secureStorage.deleteItem as jest.Mock).mockImplementation((key: string) =>
      key === SECURE_STORE_KEYS.JWT
        ? Promise.reject(new Error("keychain boom"))
        : Promise.resolve(undefined),
    );

    await expect(wipeLocalDeviceState()).resolves.toBeUndefined();

    const deleted = (secureStorage.deleteItem as jest.Mock).mock.calls.map(
      (c) => c[0],
    );
    expect(deleted).toHaveLength(Object.keys(SECURE_STORE_KEYS).length);
    warnSpy.mockRestore();
  });

  it("delegates AsyncStorage cleanup to the individual stores", async () => {
    await wipeLocalDeviceState();

    expect(dismissedJobs.clearDismissedJobs).toHaveBeenCalledTimes(1);
    expect(refundToast.clearRefundToastSeen).toHaveBeenCalledTimes(1);
  });

  it("resets in-memory singletons and the query cache", async () => {
    await wipeLocalDeviceState();

    expect(dismissedJobs.clearDismissedJobs).toHaveBeenCalledTimes(1);
    expect(refundToast.clearRefundToastSeen).toHaveBeenCalledTimes(1);
    expect(mutationQueue.clear).toHaveBeenCalledTimes(1);
    expect(queryClient.clear).toHaveBeenCalledTimes(1);
  });
});
