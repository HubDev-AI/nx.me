/**
 * Matrix tests for useCapabilities() — pure `(features × session)` derivation.
 *
 * Mocks features-context + auth-context at the module boundary so each case
 * sets the two inputs explicitly. Exercises every row of the result matrix in
 * docs/plans/2026-04-15-001-feat-feature-flags-redesign-plan.md §High-Level
 * Technical Design.
 */
import { renderHook } from "@testing-library/react-native";

import { useCapabilities } from "./capabilities";
import type { FeatureFlags } from "../constants/features";
import { buildSessionState, type SessionMode } from "./session";

jest.mock("./features-context", () => ({
  useFeatures: jest.fn(),
}));

jest.mock("./auth-context", () => ({
  useSession: jest.fn(),
}));

const featuresMod = require("./features-context") as {
  useFeatures: jest.Mock;
};
const authMod = require("./auth-context") as { useSession: jest.Mock };

type FlagOverrides = Partial<FeatureFlags>;

const BASE_FEATURES: FeatureFlags = {
  auth_required: true,
  social_enabled: false,
  share_enabled: true,
  onboarding_enabled: true,
  advisor_enabled: true,
};

function setInputs(mode: SessionMode, flags: FlagOverrides = {}) {
  featuresMod.useFeatures.mockReturnValue({
    features: { ...BASE_FEATURES, ...flags },
    isLoading: false,
  });
  authMod.useSession.mockReturnValue(buildSessionState(mode, true));
}

function render() {
  return renderHook(() => useCapabilities()).result.current;
}

describe("useCapabilities", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------- Happy paths ----------

  it("user + auth_required=true → full profile access + sign-out, no sign-in", () => {
    setInputs("user", { auth_required: true });
    const caps = render();

    expect(caps.canViewOwnProfile).toBe(true);
    expect(caps.canEditProfile).toBe(true);
    expect(caps.canViewAccountDetails).toBe(true);
    expect(caps.canDeleteAccount).toBe(true);
    expect(caps.canSignOut).toBe(true);
    expect(caps.canSignIn).toBe(false);
    expect(caps.requiresAuth).toBe(true);
  });

  it("guest + auth_required=false + social_enabled=false → guest profile without sign-in/sign-out UI", () => {
    setInputs("guest", { auth_required: false, social_enabled: false });
    const caps = render();

    expect(caps.canViewOwnProfile).toBe(true);
    expect(caps.canEditProfile).toBe(false);
    // Guests have no account record — no account details to view or delete.
    expect(caps.canViewAccountDetails).toBe(false);
    expect(caps.canDeleteAccount).toBe(false);
    // Auth feature off → neither sign-in nor sign-out make sense.
    expect(caps.canSignOut).toBe(false);
    expect(caps.canSignIn).toBe(false);
    expect(caps.canViewBlockedUsers).toBe(false);
    expect(caps.canSeeFeed).toBe(false);
    expect(caps.canReact).toBe(false);
    expect(caps.requiresAuth).toBe(false);
  });

  // ---------- Edge cases ----------

  it("user + auth_required=false → user retains profile access but auth actions hide", () => {
    setInputs("user", { auth_required: false });
    const caps = render();

    expect(caps.canViewOwnProfile).toBe(true);
    expect(caps.canEditProfile).toBe(true);
    // Even though the user is signed in, the feature is off — UI shouldn't
    // offer log-out. (Impossible runtime combo but the derivation stays pure.)
    expect(caps.canSignOut).toBe(false);
    expect(caps.canSignIn).toBe(false);
    expect(caps.canViewBlockedUsers).toBe(false);
  });

  it("anon + auth_required=true → no profile access, sign-in offered", () => {
    setInputs("anon", { auth_required: true });
    const caps = render();

    expect(caps.canViewOwnProfile).toBe(false);
    expect(caps.canSignIn).toBe(true);
    expect(caps.canSignOut).toBe(false);
    expect(caps.canEditProfile).toBe(false);
  });

  it("guest + auth_required=true (impossible at runtime) → capability layer stays pure", () => {
    // Guest tokens are not issued when auth_required=true; this row exercises
    // derivation purity rather than a real runtime state.
    setInputs("guest", { auth_required: true });
    const caps = render();

    expect(caps.canViewOwnProfile).toBe(false);
    expect(caps.canSignIn).toBe(true);
    expect(caps.canSignOut).toBe(false);
  });

  // ---------- Flag matrix (representative rows) ----------

  it.each([
    { social: true, advisor: true, share: true, onboarding: true },
    { social: false, advisor: false, share: false, onboarding: false },
    { social: true, advisor: false, share: true, onboarding: false },
    { social: false, advisor: true, share: false, onboarding: true },
  ])(
    "derives feature-capabilities for %o",
    ({ social, advisor, share, onboarding }) => {
      setInputs("user", {
        social_enabled: social,
        advisor_enabled: advisor,
        share_enabled: share,
        onboarding_enabled: onboarding,
      });
      const caps = render();

      expect(caps.canSeeFeed).toBe(social);
      expect(caps.canReact).toBe(social);
      expect(caps.canUseAdvisor).toBe(advisor);
      expect(caps.canShareGlowup).toBe(share);
      expect(caps.canShareProfile).toBe(social);
      expect(caps.canSeeOnboarding).toBe(onboarding);
    },
  );

  // ---------- Share profile: keyed to social_enabled only ----------

  it.each([
    { mode: "user" as const, social: true, expected: true },
    { mode: "user" as const, social: false, expected: false },
    { mode: "guest" as const, social: true, expected: true },
    { mode: "guest" as const, social: false, expected: false },
    { mode: "anon" as const, social: true, expected: true },
    { mode: "anon" as const, social: false, expected: false },
  ])(
    "canShareProfile tracks social_enabled regardless of session (mode=$mode, social=$social)",
    ({ mode, social, expected }) => {
      setInputs(mode, { social_enabled: social });
      expect(render().canShareProfile).toBe(expected);
    },
  );

  // ---------- Blocked users: requires auth AND social ----------

  it.each([
    { auth: true, social: true, expected: true },
    { auth: true, social: false, expected: false },
    { auth: false, social: true, expected: false },
    { auth: false, social: false, expected: false },
  ])(
    "canViewBlockedUsers needs both auth and social (auth=$auth, social=$social)",
    ({ auth, social, expected }) => {
      setInputs("user", { auth_required: auth, social_enabled: social });
      expect(render().canViewBlockedUsers).toBe(expected);
    },
  );

  // ---------- Stubs ----------

  it("canSubscribe is stubbed true until premium tiering adds a flag", () => {
    setInputs("anon");
    expect(render().canSubscribe).toBe(true);
  });
});
