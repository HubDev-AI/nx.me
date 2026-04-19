/**
 * paywall-cta — pure function mapping entitlement state to paywall CTA.
 *
 * Implements the CTA matrix from the credits-only payments spec (Unit 12).
 * No React, no side effects — testable in isolation.
 *
 * Matrix:
 * | tier | subscription_status     | blocked_reason                        | Primary CTA      | Secondary CTA |
 * |------|-------------------------|---------------------------------------|------------------|---------------|
 * | Free | none / canceled         | insufficient_credits                  | Subscribe to Pro | Buy pack      |
 * | Free | none                    | none                                  | (no paywall)     | —             |
 * | Pro  | active                  | insufficient_credits                  | Buy pack         | —             |
 * | Pro  | grace                   | insufficient_credits                  | Update card      | Buy pack      |
 * | any  | locked                  | subscription_locked_by_dispute        | Contact support  | —             |
 */

import {
  PAYWALL_BUY_PACK_PRIMARY_ACTION,
  PAYWALL_BUY_PACK_PRIMARY_LABEL,
  PAYWALL_CONTACT_SUPPORT_PRIMARY_ACTION,
  PAYWALL_CONTACT_SUPPORT_PRIMARY_LABEL,
  PAYWALL_SUBSCRIBE_PRIMARY_ACTION,
  PAYWALL_SUBSCRIBE_PRIMARY_LABEL,
  PAYWALL_SUBSCRIBE_SECONDARY_ACTION,
  PAYWALL_SUBSCRIBE_SECONDARY_LABEL,
  PAYWALL_UPDATE_CARD_PRIMARY_ACTION,
  PAYWALL_UPDATE_CARD_PRIMARY_LABEL,
  PAYWALL_UPDATE_CARD_SECONDARY_ACTION,
  PAYWALL_UPDATE_CARD_SECONDARY_LABEL,
} from "../copy/paywall";
import type { EntitlementState } from "./entitlement";

// ---------------------------------------------------------------------------
// Discriminated union types
// ---------------------------------------------------------------------------

export type CtaAction =
  | "subscribe"
  | "buy_pack"
  | "update_card"
  | "contact_support";

export interface CtaButton {
  label: string;
  action: CtaAction;
}

export type PaywallCta =
  | { type: "no_paywall" }
  | { type: "subscribe"; primary: CtaButton; secondary: CtaButton }
  | { type: "buy_pack"; primary: CtaButton }
  | { type: "update_card"; primary: CtaButton; secondary: CtaButton }
  | { type: "contact_support"; primary: CtaButton };

// ---------------------------------------------------------------------------
// Matrix implementation
// ---------------------------------------------------------------------------

/**
 * Map entitlement fields to the correct paywall CTA variant.
 *
 * Parameters match EntitlementState fields directly so the function can be
 * called with destructured values or inline for tests.
 */
export function getPaywallCta(
  tier: EntitlementState["tier"],
  subscription_status: EntitlementState["subscription_status"],
  blocked_reason: EntitlementState["blocked_reason"],
): PaywallCta {
  // Locked by dispute — highest priority, any tier
  if (subscription_status === "locked") {
    return {
      type: "contact_support",
      primary: {
        label: PAYWALL_CONTACT_SUPPORT_PRIMARY_LABEL,
        action: PAYWALL_CONTACT_SUPPORT_PRIMARY_ACTION,
      },
    };
  }

  // No block — no paywall needed
  if (blocked_reason === "none") {
    return { type: "no_paywall" };
  }

  // blocked_reason === "insufficient_credits" from here on

  if (tier === "Pro") {
    if (subscription_status === "grace") {
      return {
        type: "update_card",
        primary: {
          label: PAYWALL_UPDATE_CARD_PRIMARY_LABEL,
          action: PAYWALL_UPDATE_CARD_PRIMARY_ACTION,
        },
        secondary: {
          label: PAYWALL_UPDATE_CARD_SECONDARY_LABEL,
          action: PAYWALL_UPDATE_CARD_SECONDARY_ACTION,
        },
      };
    }
    // Pro active (or active + insufficient_credits edge case)
    return {
      type: "buy_pack",
      primary: {
        label: PAYWALL_BUY_PACK_PRIMARY_LABEL,
        action: PAYWALL_BUY_PACK_PRIMARY_ACTION,
      },
    };
  }

  // Free tier (none / canceled) with insufficient_credits
  return {
    type: "subscribe",
    primary: {
      label: PAYWALL_SUBSCRIBE_PRIMARY_LABEL,
      action: PAYWALL_SUBSCRIBE_PRIMARY_ACTION,
    },
    secondary: {
      label: PAYWALL_SUBSCRIBE_SECONDARY_LABEL,
      action: PAYWALL_SUBSCRIBE_SECONDARY_ACTION,
    },
  };
}
