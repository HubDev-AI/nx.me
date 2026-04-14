/**
 * Stripe price formatter — converts amount + ISO 4217 currency to a
 * locale-formatted display string.
 *
 * Backend returns prices as `amount_cents` (smallest currency unit)
 * + `currency` (lowercase ISO code, e.g. "usd"). Use this helper
 * everywhere price display is needed so formatting stays consistent.
 *
 * Hermes ships with `Intl.NumberFormat` via the bundled ICU data, so
 * this works on iOS + Android without extra polyfills.
 */
const PRICE_LOCALE = "en-US";

export function formatPrice(amountCents: number, currency: string): string {
  const formatter = new Intl.NumberFormat(PRICE_LOCALE, {
    style: "currency",
    currency: currency.toUpperCase(),
  });
  return formatter.format(amountCents / 100);
}
