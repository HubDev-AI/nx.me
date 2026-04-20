jest.mock("./auth", () => ({
  getStoredJwt: jest.fn(),
  storeJwt: jest.fn(),
  getRefreshToken: jest.fn(),
  storeRefreshToken: jest.fn(),
  clearAllTokens: jest.fn(),
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

const apiModule = require("./api") as typeof import("./api") & {
  restoreStoredSession?: () => Promise<string | null>;
};

describe("apiFetch", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn();
  });

  it("attaches JWT when one is stored", async () => {
    auth.getStoredJwt.mockResolvedValue("user-jwt");
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });

    await apiModule.apiFetch("/v1/entitlement");

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.headers["Authorization"]).toBe("Bearer user-jwt");
  });

  it("sends no Authorization header when no JWT is stored", async () => {
    auth.getStoredJwt.mockResolvedValue(null);
    (global.fetch as jest.Mock).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ok: true }),
    });

    await apiModule.apiFetch("/v1/features");

    const [, options] = (global.fetch as jest.Mock).mock.calls[0];
    expect(options.headers["Authorization"]).toBeUndefined();
  });

  it("refreshes on 401 and retries the original request", async () => {
    auth.getStoredJwt.mockResolvedValue("stale-jwt");
    auth.getRefreshToken.mockResolvedValue("refresh-token");
    const stale401 = {
      ok: false,
      status: 401,
      text: async () => "",
      headers: new Headers(),
      clone: function () {
        return this;
      },
    };
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(stale401)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          access_token: "fresh-jwt",
          refresh_token: "fresh-refresh",
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => ({ ok: true }),
      });

    const result = await apiModule.apiFetch<{ ok: boolean }>("/v1/entitlement");

    expect(result).toEqual({ ok: true });
    // First call = stale, second call = /auth/refresh, third call = retry with fresh JWT.
    expect((global.fetch as jest.Mock).mock.calls).toHaveLength(3);
    const [, retryOptions] = (global.fetch as jest.Mock).mock.calls[2];
    expect(retryOptions.headers["Authorization"]).toBe("Bearer fresh-jwt");
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
