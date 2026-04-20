/**
 * Female-targeted paywall copy strings.
 *
 * All copy is written for a majority-female audience. No beard/male-coded
 * examples. Tone: warm, encouraging, never pushy.
 *
 * Keep all user-facing strings here — no magic strings in UI components.
 */
import {
  FREE_SIGNUP_GLOWUPS,
  FREE_WEEKLY_REGEN_GLOWUPS,
  PRO_MONTHLY_GLOWUPS,
  PRO_MONTHLY_PRICE_USD,
} from "../constants/pricing";
import type { FeatureFlags } from "../constants/features";

// ---------------------------------------------------------------------------
// Subscribe CTA
// ---------------------------------------------------------------------------

export const PAYWALL_SUBSCRIBE_PRIMARY_LABEL = "Unlock Pro";
export const PAYWALL_SUBSCRIBE_PRIMARY_ACTION = "subscribe";

// ---------------------------------------------------------------------------
// Update card CTA (grace period)
// ---------------------------------------------------------------------------

export const PAYWALL_UPDATE_CARD_PRIMARY_LABEL = "Update payment info";
export const PAYWALL_UPDATE_CARD_PRIMARY_ACTION = "update_card";

// ---------------------------------------------------------------------------
// Contact support CTA (dispute / locked)
// ---------------------------------------------------------------------------

export const PAYWALL_CONTACT_SUPPORT_PRIMARY_LABEL = "Contact support";
export const PAYWALL_CONTACT_SUPPORT_PRIMARY_ACTION = "contact_support";

// ---------------------------------------------------------------------------
// Header + sub-copy by scenario
// ---------------------------------------------------------------------------

export const PAYWALL_HEADER_SUBSCRIBE = "Ready for your glow-up?";

/**
 * Subscribe-scenario subheader. Conditional on the weekly-regen kill-switch
 * so we never promise a refill we cannot deliver. Callers pass the resolved
 * `features` registry from `useFeatures()`; the `?? false` guard treats a
 * missing field (older backend rollout) as "cron paused" per the no-env-
 * fallbacks rule.
 */
export function buildPaywallSubheaderSubscribe(features: FeatureFlags): string {
  const weeklyEnabled = features.weekly_free_grant_enabled ?? false;
  const freeLine = weeklyEnabled
    ? `Free: ${FREE_SIGNUP_GLOWUPS} glow-ups to start, plus ${FREE_WEEKLY_REGEN_GLOWUPS} every week.`
    : `Free: ${FREE_SIGNUP_GLOWUPS} glow-ups to start.`;
  return `${freeLine} Pro: ${PRO_MONTHLY_GLOWUPS} a month for ${PRO_MONTHLY_PRICE_USD}.`;
}

export const PAYWALL_HEADER_UPDATE_CARD = "Let's sort out your billing";
export const PAYWALL_SUBHEADER_UPDATE_CARD =
  "Update your payment info to keep Pro active.";

export const PAYWALL_HEADER_CONTACT_SUPPORT = "We're here to help";
export const PAYWALL_SUBHEADER_CONTACT_SUPPORT =
  "Your account needs a quick review. Reach out and we'll get you sorted.";
