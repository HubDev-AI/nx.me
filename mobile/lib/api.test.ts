jest.mock("./auth", () => ({
  getStoredJwt: jest.fn(),
  storeJwt: jest.fn(),
  getRefreshToken: jest.fn(),
  storeRefreshToken: jest.fn(),
  clearAllTokens: jest.fn(),
}));

jest.mock("./guest-session", () => ({
  getStoredGuestToken: jest.fn(),
  getOrCreateGuestToken: jest.fn(),
}));

jest.mock("./secure-storage", () => ({
  getItem: jest.fn(),
  setItem: jest.fn(),
  deleteItem: jest.fn(),
}));

const auth = require("./auth") as {
  getStoredJwt: jest.Mock;
  storeJwt: jest.Mock;
  getRefreshToken: jest.Mock;
  storeRefreshToken: jest.Mock;
  clearAllTokens: jest.Mock;
};

const guestSession = require("./guest-session") as {
  getStoredGuestToken: jest.Mock;
  getOrCreateGuestToken: jest.Mock;
};

const secureStorage = require("./secure-storage") as {
  deleteItem: jest.Mock;
};

const featuresState = require("./features-state") as {
  setAuthRequired: (v: boolean) => void;
};

const apiModule = require("./api") as typeof import("./api") & {
  restoreStoredSession?: () => Promise<string | null>;
};

describe("apiFetch", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
    featuresState.setAuthRequired(true);
  });

  it("does not provision a guest session when auth is required (prod default)", async () => {
    auth.getStoredJwt.mockResolvedValue(null);
    guestSession.getStoredGuestToken.mockResolvedValue(null);
    guestSession.getOrCreateGuestToken.mockResolvedValue("guest-token");
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });

    await apiModule.apiFetch("/v1/public/cards/alice");

    expect(guestSession.getOrCreateGuestToken).not.toHaveBeenCalled();
    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.headers["X-Guest-Token"]).toBeUndefined();
  });

  it("auto-provisions a guest token when auth_required is false and none stored", async () => {
    featuresState.setAuthRequired(false);
    auth.getStoredJwt.mockResolvedValue(null);
    guestSession.getStoredGuestToken.mockResolvedValue(null);
    guestSession.getOrCreateGuestToken.mockResolvedValue("fresh-guest-token");
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });

    await apiModule.apiFetch("/v1/entitlement");

    expect(guestSession.getOrCreateGuestToken).toHaveBeenCalledTimes(1);
    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.headers["X-Guest-Token"]).toBe("fresh-guest-token");
  });

  it("rotates a stale guest token on 401 and retries once", async () => {
    featuresState.setAuthRequired(false);
    auth.getStoredJwt.mockResolvedValue(null);
    guestSession.getStoredGuestToken.mockResolvedValue("stale-token");
    guestSession.getOrCreateGuestToken.mockResolvedValue("new-token");
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce({
        ok: false,
        status: 401,
        text: async () => "",
        headers: new Headers(),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      });

    const result = await apiModule.apiFetch<{ ok: boolean }>("/v1/entitlement");

    expect(result).toEqual({ ok: true });
    expect(secureStorage.deleteItem).toHaveBeenCalledWith("nxme_guest_token");
    expect(guestSession.getOrCreateGuestToken).toHaveBeenCalledTimes(1);
    expect((global.fetch as jest.Mock).mock.calls).toHaveLength(2);
    const [, retryOptions] = (global.fetch as jest.Mock).mock.calls[1];
    expect(retryOptions.headers["X-Guest-Token"]).toBe("new-token");
  });

  it("restores the stored session from the refresh token", async () => {
    auth.getRefreshToken.mockResolvedValue("refresh-token");
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      json: async () => ({
        access_token: "new-access-token",
        refresh_token: "new-refresh-token",
      }),
    });

    expect(typeof apiModule.restoreStoredSession).toBe("function");
    const token = await apiModule.restoreStoredSession?.();

    expect(token).toBe("new-access-token");
    expect(auth.storeJwt).toHaveBeenCalledWith("new-access-token");
    expect(auth.storeRefreshToken).toHaveBeenCalledWith("new-refresh-token");
  });
});
