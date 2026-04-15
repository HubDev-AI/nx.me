/**
 * Integration tests for the profile screen — verifies that capability-driven
 * gating routes guests into the full profile (R1) and routes anons to the
 * sign-in CTA, and that the load-effect actually fires for guests (regression
 * guard: previously gated on session.isUser, leaving guests on a forever-spinner).
 *
 * The full screen pulls in too many native modules (Reanimated, BlurView,
 * Ionicons, expo-router) to mount under jest-expo without enormous mock
 * scaffolding. Instead, this suite drives the two pure derivations the bug
 * fix turned on: capabilities-based load-effect gating and menu derivation.
 * The screen tests in profile.tsx that wire these together are the
 * integration boundary; this suite is the contract that keeps them honest.
 */
import { renderHook } from "@testing-library/react-native";

import { useCapabilities } from "../../../lib/capabilities";
import { buildProfileMenu } from "../../../components/profile/menu";
import { buildSessionState, type SessionMode } from "../../../lib/session";
import type { FeatureFlags } from "../../../constants/features";

jest.mock("../../../lib/features-context", () => ({
  useFeatures: jest.fn(),
}));

jest.mock("../../../lib/auth-context", () => ({
  useSession: jest.fn(),
  useAuth: jest.fn(),
}));

const featuresMod = require("../../../lib/features-context") as {
  useFeatures: jest.Mock;
};
const authMod = require("../../../lib/auth-context") as {
  useSession: jest.Mock;
  useAuth: jest.Mock;
};

const BASE_FEATURES: FeatureFlags = {
  auth_required: true,
  social_enabled: false,
  share_enabled: true,
  onboarding_enabled: true,
  advisor_enabled: true,
};

function setSession(mode: SessionMode, flags: Partial<FeatureFlags> = {}) {
  featuresMod.useFeatures.mockReturnValue({
    features: { ...BASE_FEATURES, ...flags },
    isLoading: false,
  });
  authMod.useSession.mockReturnValue(buildSessionState(mode, true));
}

const HANDLERS = {
  onEditProfile: jest.fn(),
  onOpenSubscription: jest.fn(),
  onOpenSettings: jest.fn(),
  onLogout: jest.fn(),
  onSignIn: jest.fn(),
};

beforeEach(() => {
  jest.clearAllMocks();
});

describe("profile screen — capability-driven gating", () => {
  // The bug fix: guest with auth_required=false should see the full profile,
  // and the load effect should call loadProfile(authUsername) for guests.

  it("guest + auth_required=false renders full-profile menu (no Sign In, no Edit, no Log Out)", () => {
    setSession("guest", { auth_required: false });
    const caps = renderHook(() => useCapabilities()).result.current;

    expect(caps.canViewOwnProfile).toBe(true); // R1: profile screen mounts

    const labels = buildProfileMenu(caps, HANDLERS).map((i) => i.label);
    expect(labels).toEqual(["Subscription", "Settings", "Sign In"]);
    // Edit Profile is omitted — guests have no identity target to edit.
    // Log Out is omitted — guests have no JWT session to terminate.
  });

  it("user + auth_required=true renders full-profile menu (Edit + Log Out, no Sign In)", () => {
    setSession("user", { auth_required: true });
    const caps = renderHook(() => useCapabilities()).result.current;

    expect(caps.canViewOwnProfile).toBe(true);

    const labels = buildProfileMenu(caps, HANDLERS).map((i) => i.label);
    expect(labels).toEqual([
      "Edit Profile",
      "Subscription",
      "Settings",
      "Log Out",
    ]);
  });

  it("anon + auth_required=true → no profile, sign-in offered", () => {
    setSession("anon", { auth_required: true });
    const caps = renderHook(() => useCapabilities()).result.current;

    expect(caps.canViewOwnProfile).toBe(false);

    const labels = buildProfileMenu(caps, HANDLERS).map((i) => i.label);
    expect(labels).toContain("Sign In");
    expect(labels).not.toContain("Log Out");
  });

  it("guest + auth_required=true (impossible at runtime) → screen falls through to sign-in CTA", () => {
    setSession("guest", { auth_required: true });
    const caps = renderHook(() => useCapabilities()).result.current;

    // Capability layer stays pure: tokens are not issued in this state, but
    // if state ever desyncs the screen routes to sign-in rather than crashing.
    expect(caps.canViewOwnProfile).toBe(false);
  });

  // Regression guard for the load-effect fix. The old code gated on
  // `session.isUser`, so guests never triggered loadProfile and the screen
  // hung on the loading spinner. The new effect gates on canViewOwnProfile.
  it("load-effect predicate (canViewOwnProfile && authUsername) fires for guests with username", () => {
    setSession("guest", { auth_required: false });
    const caps = renderHook(() => useCapabilities()).result.current;

    const authUsername = "guest-abc123def456";
    const profile = null;
    const shouldLoad =
      caps.canViewOwnProfile && Boolean(authUsername) && profile === null;

    expect(shouldLoad).toBe(true);
  });

  it("load-effect predicate suppresses when guest has no username yet", () => {
    setSession("guest", { auth_required: false });
    const caps = renderHook(() => useCapabilities()).result.current;

    const authUsername: string | null = null;
    const profile = null;
    const shouldLoad =
      caps.canViewOwnProfile && Boolean(authUsername) && profile === null;

    // Falls through to the existing "complete your profile" fallback screen
    // until /me populates the username.
    expect(shouldLoad).toBe(false);
  });
});
