import * as secureStorage from "../secure-storage";
import * as Crypto from "expo-crypto";
import { SECURE_STORE_KEYS } from "../../constants/config";
import { getOrCreateInstallUuid, isValidUuidV4 } from "../install-uuid";

jest.mock("expo-crypto", () => ({
  randomUUID: jest.fn(),
}));

const mockGetItem = jest.spyOn(secureStorage, "getItem");
const mockSetItem = jest.spyOn(secureStorage, "setItem");
const mockDeleteItem = jest.spyOn(secureStorage, "deleteItem");
const mockRandomUUID = Crypto.randomUUID as jest.Mock;

const VALID_UUID = "550e8400-e29b-41d4-a716-446655440000";
const ANOTHER_UUID = "6ba7b810-9dad-41d4-80b4-00c04fd430c8";

beforeEach(() => {
  jest.clearAllMocks();
  mockSetItem.mockResolvedValue(undefined);
  mockDeleteItem.mockResolvedValue(undefined);
});

describe("isValidUuidV4", () => {
  it("returns true for a valid UUID v4", () => {
    expect(isValidUuidV4("550e8400-e29b-41d4-a716-446655440000")).toBe(true);
    expect(isValidUuidV4("6ba7b810-9dad-41d4-80b4-00c04fd430c8")).toBe(true);
  });

  it("returns false for UUID v1 (version digit is 1)", () => {
    expect(isValidUuidV4("550e8400-e29b-11d4-a716-446655440000")).toBe(false);
  });

  it("returns false for truncated strings", () => {
    expect(isValidUuidV4("550e8400-e29b-41d4")).toBe(false);
  });

  it("returns false for empty string", () => {
    expect(isValidUuidV4("")).toBe(false);
  });

  it("returns false for random garbage", () => {
    expect(isValidUuidV4("not-a-uuid")).toBe(false);
  });
});

describe("getOrCreateInstallUuid", () => {
  it("generates and persists a UUID on first call (nothing stored)", async () => {
    mockGetItem.mockResolvedValue(null);
    mockRandomUUID.mockReturnValue(VALID_UUID);

    const result = await getOrCreateInstallUuid();

    expect(mockRandomUUID).toHaveBeenCalledTimes(1);
    expect(mockSetItem).toHaveBeenCalledWith(
      SECURE_STORE_KEYS.INSTALL_UUID,
      VALID_UUID,
    );
    expect(result).toBe(VALID_UUID);
  });

  it("returns the stored UUID without generating a new one on second call", async () => {
    mockGetItem.mockResolvedValue(VALID_UUID);

    const result = await getOrCreateInstallUuid();

    expect(mockRandomUUID).not.toHaveBeenCalled();
    expect(mockSetItem).not.toHaveBeenCalled();
    expect(result).toBe(VALID_UUID);
  });

  it("regenerates when stored value is corrupted (not a valid UUID v4)", async () => {
    mockGetItem.mockResolvedValue("corrupted-garbage-value");
    mockRandomUUID.mockReturnValue(ANOTHER_UUID);

    const result = await getOrCreateInstallUuid();

    expect(mockDeleteItem).toHaveBeenCalledWith(SECURE_STORE_KEYS.INSTALL_UUID);
    expect(mockRandomUUID).toHaveBeenCalledTimes(1);
    expect(mockSetItem).toHaveBeenCalledWith(
      SECURE_STORE_KEYS.INSTALL_UUID,
      ANOTHER_UUID,
    );
    expect(result).toBe(ANOTHER_UUID);
  });

  it("regenerates when stored value is a UUID v1 (wrong version)", async () => {
    // UUID v1 — version digit is 1, not 4
    mockGetItem.mockResolvedValue("550e8400-e29b-11d4-a716-446655440000");
    mockRandomUUID.mockReturnValue(VALID_UUID);

    const result = await getOrCreateInstallUuid();

    expect(mockDeleteItem).toHaveBeenCalled();
    expect(mockRandomUUID).toHaveBeenCalledTimes(1);
    expect(result).toBe(VALID_UUID);
  });

  it("awaits setItem before returning the UUID (write is not fire-and-forget)", async () => {
    // If setItem were fire-and-forget the resolved value would be returned
    // before the mock's promise settles. We track completion order to prove
    // the function waits for the write.
    mockGetItem.mockResolvedValue(null);
    mockRandomUUID.mockReturnValue(VALID_UUID);

    const completionOrder: string[] = [];

    mockSetItem.mockImplementation(async () => {
      // Yield to the microtask queue so that a fire-and-forget write would
      // let the caller return before reaching this point.
      await Promise.resolve();
      completionOrder.push("setItem");
    });

    const resultPromise = getOrCreateInstallUuid();
    const result = await resultPromise;
    completionOrder.push("returned");

    // setItem must have completed before the function returned the UUID.
    expect(completionOrder).toEqual(["setItem", "returned"]);
    expect(result).toBe(VALID_UUID);
  });
});
