/**
 * Female-targeted paywall copy strings.
 *
 * All copy is written for a majority-female audience. No beard/male-coded
 * examples. Tone: warm, encouraging, never pushy.
 *
 * Keep all user-facing strings here — no magic strings in UI components.
 */

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
// NOTE: the concrete Pro cap ("30 glow-ups a month…") lands in Unit 2 of
// plan 2026-04-20-002 alongside the MONTHLY_ALLOTMENT_MILLI / ADA_COST_MILLI
// constants. This line will be replaced there.
export const PAYWALL_SUBHEADER_SUBSCRIBE = "Go Pro for unlimited looks.";

export const PAYWALL_HEADER_UPDATE_CARD = "Let's sort out your billing";
export const PAYWALL_SUBHEADER_UPDATE_CARD =
  "Update your payment info to keep Pro active.";

export const PAYWALL_HEADER_CONTACT_SUPPORT = "We're here to help";
export const PAYWALL_SUBHEADER_CONTACT_SUPPORT =
  "Your account needs a quick review. Reach out and we'll get you sorted.";
