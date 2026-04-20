import { getPaywallCta } from "../paywall-cta";
import type { EntitlementState } from "../entitlement";

// ---------------------------------------------------------------------------
// Type aliases for readability
// ---------------------------------------------------------------------------
type Tier = EntitlementState["tier"];
type Status = EntitlementState["subscription_status"];
type Reason = EntitlementState["blocked_reason"];

// ---------------------------------------------------------------------------
// CTA matrix tests (post-pack-removal matrix — plan 2026-04-20-002 Unit 1)
// ---------------------------------------------------------------------------

describe("getPaywallCta — CTA matrix", () => {
  it("Free + none + insufficient_credits → subscribe", () => {
    const cta = getPaywallCta(
      "Free" as Tier,
      "none" as Status,
      "insufficient_credits" as Reason,
    );
    expect(cta.type).toBe("subscribe");
    if (cta.type === "subscribe") {
      expect(cta.primary.action).toBe("subscribe");
      expect(typeof cta.primary.label).toBe("string");
      expect(cta.primary.label.length).toBeGreaterThan(0);
      expect("secondary" in cta).toBe(false);
    }
  });

  it("Free + canceled + insufficient_credits → subscribe", () => {
    const cta = getPaywallCta(
      "Free" as Tier,
      "canceled" as Status,
      "insufficient_credits" as Reason,
    );
    expect(cta.type).toBe("subscribe");
  });

  it("Free + none + none → no_paywall", () => {
    const cta = getPaywallCta("Free" as Tier, "none" as Status, "none" as Reason);
    expect(cta.type).toBe("no_paywall");
  });

  it("Pro + active + insufficient_credits → wait_for_refill", () => {
    const cta = getPaywallCta(
      "Pro" as Tier,
      "active" as Status,
      "insufficient_credits" as Reason,
    );
    expect(cta.type).toBe("wait_for_refill");
    // wait_for_refill has no buttons — caller renders the refill date from
    // EntitlementState.period_end.
    expect("primary" in cta).toBe(false);
    expect("secondary" in cta).toBe(false);
  });

  it("Pro + grace + insufficient_credits → update_card (no secondary)", () => {
    const cta = getPaywallCta(
      "Pro" as Tier,
      "grace" as Status,
      "insufficient_credits" as Reason,
    );
    expect(cta.type).toBe("update_card");
    if (cta.type === "update_card") {
      expect(cta.primary.action).toBe("update_card");
      expect("secondary" in cta).toBe(false);
    }
  });

  it("Free + locked + subscription_locked_by_dispute → contact_support", () => {
    const cta = getPaywallCta(
      "Free" as Tier,
      "locked" as Status,
      "subscription_locked_by_dispute" as Reason,
    );
    expect(cta.type).toBe("contact_support");
    if (cta.type === "contact_support") {
      expect(cta.primary.action).toBe("contact_support");
      expect("secondary" in cta).toBe(false);
    }
  });

  it("Pro + locked + subscription_locked_by_dispute → contact_support", () => {
    const cta = getPaywallCta(
      "Pro" as Tier,
      "locked" as Status,
      "subscription_locked_by_dispute" as Reason,
    );
    expect(cta.type).toBe("contact_support");
  });

  it("locked overrides blocked_reason=none → contact_support", () => {
    const cta = getPaywallCta("Pro" as Tier, "locked" as Status, "none" as Reason);
    expect(cta.type).toBe("contact_support");
  });

  it("Pro + none + none → no_paywall", () => {
    const cta = getPaywallCta("Pro" as Tier, "none" as Status, "none" as Reason);
    expect(cta.type).toBe("no_paywall");
  });

  it("Pro + canceled + none → no_paywall", () => {
    const cta = getPaywallCta(
      "Pro" as Tier,
      "canceled" as Status,
      "none" as Reason,
    );
    expect(cta.type).toBe("no_paywall");
  });
});

// ---------------------------------------------------------------------------
// Label non-emptiness (female-targeted copy must be set on every variant
// that renders a button).
// ---------------------------------------------------------------------------
describe("getPaywallCta — labels are non-empty strings", () => {
  const scenarios: [Tier, Status, Reason][] = [
    ["Free", "none", "insufficient_credits"],
    ["Free", "canceled", "insufficient_credits"],
    ["Pro", "grace", "insufficient_credits"],
    ["Free", "locked", "subscription_locked_by_dispute"],
    ["Pro", "locked", "subscription_locked_by_dispute"],
  ];

  it.each(scenarios)(
    "tier=%s status=%s reason=%s → primary label non-empty",
    (tier, status, reason) => {
      const cta = getPaywallCta(tier, status, reason);
      if (
        cta.type !== "no_paywall" &&
        cta.type !== "wait_for_refill"
      ) {
        expect(cta.primary.label.trim().length).toBeGreaterThan(0);
      }
    },
  );
});
