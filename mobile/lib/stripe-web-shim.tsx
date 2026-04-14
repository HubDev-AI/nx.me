/**
 * Platform-specific Stripe shim.
 * On native: re-exports real StripeProvider + useStripe.
 * On web: provides a passthrough wrapper + a stub useStripe that rejects
 *         with a clear message (web clients cannot present Payment Sheet).
 */
export { StripeProvider, useStripe } from "@stripe/stripe-react-native";
