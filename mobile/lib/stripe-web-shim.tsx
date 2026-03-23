/**
 * Platform-specific Stripe shim.
 * On native: re-exports real StripeProvider.
 * On web: provides a passthrough wrapper (Stripe is native-only).
 */
export { StripeProvider } from "@stripe/stripe-react-native";
