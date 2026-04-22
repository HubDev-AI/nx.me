/**
 * Matrix tests for useCapabilities() — pure `(features × session)` derivation.
 *
 * Mocks features-context + auth-context at the module boundary so each case
 * sets the two inputs explicitly.
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

jest.mock("./hooks/use-subscription-tier", () => ({
  useSubscriptionTier: jest.fn(),
}));

const featuresMod = require("./features-context") as {
  useFeatures: jest.Mock;
};
const authMod = require("./auth-context") as { useSession: jest.Mock };
const tierMod = require("./hooks/use-subscription-tier") as {
  useSubscriptionTier: jest.Mock;
};

type FlagOverrides = Partial<FeatureFlags>;

const BASE_FEATURES: FeatureFlags = {
  social_enabled: false,
  share_enabled: true,
  onboarding_enabled: true,
  advisor_enabled: true,
  weekly_free_grant_enabled: true,
  makeup_enabled: false,
};

function setInputs(
  mode: SessionMode,
  flags: FlagOverrides = {},
  tier: "Free" | "Pro" | null = null,
) {
  featuresMod.useFeatures.mockReturnValue({
    features: { ...BASE_FEATURES, ...flags },
    isLoading: false,
  });
  authMod.useSession.mockReturnValue(buildSessionState(mode, true));
  tierMod.useSubscriptionTier.mockReturnValue(tier);
}

function render() {
  return renderHook(() => useCapabilities()).result.current;
}

describe("useCapabilities", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  // ---------- Happy paths ----------

  it("user → full profile access + sign-out, no sign-in", () => {
    setInputs("user");
    const caps = render();

    expect(caps.canViewOwnProfile).toBe(true);
    expect(caps.canEditProfile).toBe(true);
    expect(caps.canViewAccountDetails).toBe(true);
    expect(caps.canDeleteAccount).toBe(true);
    expect(caps.canSignOut).toBe(true);
    expect(caps.canSignIn).toBe(false);
  });

  // ---------- Edge cases ----------

  it("anon → no profile access, sign-in offered", () => {
    setInputs("anon");
    const caps = render();

    expect(caps.canViewOwnProfile).toBe(false);
    expect(caps.canSignIn).toBe(true);
    expect(caps.canSignOut).toBe(false);
    expect(caps.canEditProfile).toBe(false);
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
    { mode: "anon" as const, social: true, expected: true },
    { mode: "anon" as const, social: false, expected: false },
  ])(
    "canShareProfile tracks social_enabled regardless of session (mode=$mode, social=$social)",
    ({ mode, social, expected }) => {
      setInputs(mode, { social_enabled: social });
      expect(render().canShareProfile).toBe(expected);
    },
  );

  // ---------- Blocked users: tied to social_enabled ----------

  it.each([
    { social: true, expected: true },
    { social: false, expected: false },
  ])(
    "canViewBlockedUsers tracks social_enabled (social=$social)",
    ({ social, expected }) => {
      setInputs("user", { social_enabled: social });
      expect(render().canViewBlockedUsers).toBe(expected);
    },
  );

  // ---------- Publish glowup: requires real user AND social ----------

  it.each([
    { mode: "user" as const, social: true, expected: true },
    { mode: "user" as const, social: false, expected: false },
    { mode: "anon" as const, social: true, expected: false },
    { mode: "anon" as const, social: false, expected: false },
  ])(
    "canPublishGlowup requires real user AND social_enabled (mode=$mode, social=$social)",
    ({ mode, social, expected }) => {
      setInputs(mode, { social_enabled: social });
      expect(render().canPublishGlowup).toBe(expected);
    },
  );

  // ---------- Stubs ----------

  it("canSubscribe is stubbed true until premium tiering adds a flag", () => {
    setInputs("anon");
    expect(render().canSubscribe).toBe(true);
  });

  // ---------- canUseMakeup: makeup_enabled × tier × session ----------

  it.each([
    { tier: "Pro" as const, makeup_enabled: true, expected: true },
    { tier: "Free" as const, makeup_enabled: true, expected: false },
    { tier: null, makeup_enabled: true, expected: false },
    { tier: "Pro" as const, makeup_enabled: false, expected: false },
  ])(
    "canUseMakeup: makeup_enabled=$makeup_enabled, tier=$tier → $expected",
    ({ tier, makeup_enabled, expected }) => {
      setInputs("user", { makeup_enabled }, tier);
      expect(render().canUseMakeup).toBe(expected);
    },
  );

  it("canUseMakeup is false for anon even with Pro tier + makeup_enabled", () => {
    setInputs("anon", { makeup_enabled: true }, "Pro");
    expect(render().canUseMakeup).toBe(false);
  });
});
