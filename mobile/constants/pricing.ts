/**
 * Pricing constants — canonical UI copy for paywall / subscription surfaces.
 *
 * Mirror of the backend `plan_versions` (v1 Pro row) values. When operators
 * rotate a plan version, the backend returns the new divisors via
 * `purchase_options` + entitlement — UI should prefer those dynamic values
 * and fall back to these constants only for pre-auth / loading states where
 * the entitlement response is not yet available.
 *
 * No magic strings / numbers in copy files — every user-visible pricing
 * number routes through here.
 */

/** Pro plan size — one billing period. */
export const PRO_MONTHLY_GLOWUPS = 30;
export const PRO_MONTHLY_ADA_APPROX = 200;
export const PRO_MONTHLY_PRICE_USD = "$9.99";

/** Free plan — day-1 allotment + recurring regen. */
export const FREE_SIGNUP_GLOWUPS = 3;
export const FREE_WEEKLY_REGEN_GLOWUPS = 1;
