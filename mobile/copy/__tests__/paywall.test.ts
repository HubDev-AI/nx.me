/**
 * Unit 3 regression tests — Free-line copy conditional on the
 * weekly_free_grant kill-switch (plan 2026-04-20-002).
 */
import { buildPaywallSubheaderSubscribe } from "../paywall";
import type { FeatureFlags } from "../../constants/features";

const BASE_FLAGS: FeatureFlags = {
  social_enabled: false,
  share_enabled: true,
  onboarding_enabled: true,
  advisor_enabled: true,
  weekly_free_grant_enabled: true,
  makeup_enabled: false,
};

describe("buildPaywallSubheaderSubscribe", () => {
  it("mentions weekly regen when the kill-switch is live", () => {
    const copy = buildPaywallSubheaderSubscribe({
      ...BASE_FLAGS,
      weekly_free_grant_enabled: true,
    });
    expect(copy).toMatch(/every week/i);
    expect(copy).toMatch(/3 glow-ups to start/);
    expect(copy).toMatch(/30 a month/);
    expect(copy).toMatch(/\$9\.99/);
  });

  it("omits the weekly regen clause when the kill-switch is paused", () => {
    const copy = buildPaywallSubheaderSubscribe({
      ...BASE_FLAGS,
      weekly_free_grant_enabled: false,
    });
    expect(copy).not.toMatch(/every week/i);
    expect(copy).toMatch(/3 glow-ups to start/);
    expect(copy).toMatch(/30 a month/);
  });

  it("fails closed when the field is absent from the response", () => {
    // Simulate an older backend that does not include the field.
    const copy = buildPaywallSubheaderSubscribe({
      ...BASE_FLAGS,
      weekly_free_grant_enabled: undefined as unknown as boolean,
    });
    expect(copy).not.toMatch(/every week/i);
  });

  it("never contains the word 'unlimited'", () => {
    for (const enabled of [true, false]) {
      const copy = buildPaywallSubheaderSubscribe({
        ...BASE_FLAGS,
        weekly_free_grant_enabled: enabled,
      });
      expect(copy.toLowerCase()).not.toContain("unlimited");
    }
  });
});
