import { act, renderHook } from "@testing-library/react-native";

const mockSetAuthenticated = jest.fn();
const mockSetUsername = jest.fn();

jest.mock("../lib/api", () => ({
  apiFetch: jest.fn(),
}));

jest.mock("../lib/auth", () => ({
  storeJwt: jest.fn(),
  storeRefreshToken: jest.fn(),
}));

jest.mock("../lib/social-auth", () => ({
  signInWithGoogle: jest.fn(),
  signInWithApple: jest.fn(),
  signInWithTikTok: jest.fn(),
}));

jest.mock("../lib/errors", () => ({
  parseApiError: jest.fn((error: unknown) => error),
}));

jest.mock("../lib/auth-context", () => ({
  useAuth: () => ({
    setAuthenticated: mockSetAuthenticated,
    setUsername: mockSetUsername,
  }),
}));

const { apiFetch } = require("../lib/api") as {
  apiFetch: jest.Mock;
};
const { storeJwt, storeRefreshToken } = require("../lib/auth") as {
  storeJwt: jest.Mock;
  storeRefreshToken: jest.Mock;
};
const { signInWithGoogle } = require("../lib/social-auth") as {
  signInWithGoogle: jest.Mock;
};

describe("useSocialAuth", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("hydrates the username after Google login succeeds", async () => {
    signInWithGoogle.mockResolvedValue({ idToken: "google-id-token" });
    apiFetch.mockResolvedValue({
      user_id: "user-1",
      username: "alice",
      access_token: "at-123",
      refresh_token: "rt-456",
      expires_at: 1710720000,
    });

    const { useSocialAuth } = require("./useSocialAuth") as typeof import("./useSocialAuth");
    const { result } = renderHook(() => useSocialAuth());

    await act(async () => {
      await result.current.handleGoogleLogin();
    });

    expect(storeJwt).toHaveBeenCalledWith("at-123");
    expect(storeRefreshToken).toHaveBeenCalledWith("rt-456");
    expect(mockSetAuthenticated).toHaveBeenCalledWith(true);
    expect(mockSetUsername).toHaveBeenCalledWith("alice");
  });
});
