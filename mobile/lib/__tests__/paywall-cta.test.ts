import { getPaywallCta } from "../paywall-cta";
import type { EntitlementState } from "../entitlement";

// ---------------------------------------------------------------------------
// Type aliases for readability
// ---------------------------------------------------------------------------
type Tier = EntitlementState["tier"];
type Status = EntitlementState["subscription_status"];
type Reason = EntitlementState["blocked_reason"];

// ---------------------------------------------------------------------------
// CTA matrix tests
// ---------------------------------------------------------------------------

describe("getPaywallCta — CTA matrix", () => {
  // | Free | none / canceled | insufficient_credits | Subscribe to Pro | Buy pack |
  it("Free + none + insufficient_credits → subscribe (primary) + buy_pack (secondary)", () => {
    const cta = getPaywallCta("Free" as Tier, "none" as Status, "insufficient_credits" as Reason);
    expect(cta.type).toBe("subscribe");
    if (cta.type === "subscribe") {
      expect(cta.primary.action).toBe("subscribe");
      expect(cta.secondary.action).toBe("buy_pack");
      expect(typeof cta.primary.label).toBe("string");
      expect(cta.primary.label.length).toBeGreaterThan(0);
      expect(typeof cta.secondary.label).toBe("string");
      expect(cta.secondary.label.length).toBeGreaterThan(0);
    }
  });

  it("Free + canceled + insufficient_credits → subscribe", () => {
    const cta = getPaywallCta("Free" as Tier, "canceled" as Status, "insufficient_credits" as Reason);
    expect(cta.type).toBe("subscribe");
  });

  // | Free | none | none | (no paywall) | — |
  it("Free + none + none → no_paywall", () => {
    const cta = getPaywallCta("Free" as Tier, "none" as Status, "none" as Reason);
    expect(cta.type).toBe("no_paywall");
  });

  // | Pro  | active | insufficient_credits | Buy pack | — |
  it("Pro + active + insufficient_credits → buy_pack (no secondary)", () => {
    const cta = getPaywallCta("Pro" as Tier, "active" as Status, "insufficient_credits" as Reason);
    expect(cta.type).toBe("buy_pack");
    if (cta.type === "buy_pack") {
      expect(cta.primary.action).toBe("buy_pack");
      expect(typeof cta.primary.label).toBe("string");
      expect(cta.primary.label.length).toBeGreaterThan(0);
      // buy_pack has no secondary
      expect("secondary" in cta).toBe(false);
    }
  });

  // | Pro  | grace | insufficient_credits | Update card | Buy pack |
  it("Pro + grace + insufficient_credits → update_card (primary) + buy_pack (secondary)", () => {
    const cta = getPaywallCta("Pro" as Tier, "grace" as Status, "insufficient_credits" as Reason);
    expect(cta.type).toBe("update_card");
    if (cta.type === "update_card") {
      expect(cta.primary.action).toBe("update_card");
      expect(cta.secondary.action).toBe("buy_pack");
    }
  });

  // | any | locked | subscription_locked_by_dispute | Contact support | — |
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

  // locked is highest priority — overrides blocked_reason=none
  it("locked overrides blocked_reason=none → contact_support", () => {
    const cta = getPaywallCta("Pro" as Tier, "locked" as Status, "none" as Reason);
    expect(cta.type).toBe("contact_support");
  });

  // Pro + none + none → no_paywall
  it("Pro + none + none → no_paywall", () => {
    const cta = getPaywallCta("Pro" as Tier, "none" as Status, "none" as Reason);
    expect(cta.type).toBe("no_paywall");
  });

  // Pro + canceled + none → no_paywall (canceled but not blocked)
  it("Pro + canceled + none → no_paywall", () => {
    const cta = getPaywallCta("Pro" as Tier, "canceled" as Status, "none" as Reason);
    expect(cta.type).toBe("no_paywall");
  });
});

// ---------------------------------------------------------------------------
// Label non-emptiness (female-targeted copy must be set)
// ---------------------------------------------------------------------------
describe("getPaywallCta — labels are non-empty strings", () => {
  const scenarios: [Tier, Status, Reason][] = [
    ["Free", "none", "insufficient_credits"],
    ["Free", "canceled", "insufficient_credits"],
    ["Pro", "active", "insufficient_credits"],
    ["Pro", "grace", "insufficient_credits"],
    ["Free", "locked", "subscription_locked_by_dispute"],
    ["Pro", "locked", "subscription_locked_by_dispute"],
  ];

  it.each(scenarios)(
    "tier=%s status=%s reason=%s → primary label non-empty",
    (tier, status, reason) => {
      const cta = getPaywallCta(tier, status, reason);
      if (cta.type !== "no_paywall") {
        expect(cta.primary.label.trim().length).toBeGreaterThan(0);
      }
    },
  );
});
