/**
 * Web shim for StripeProvider + useStripe — renders children only and
 * exposes a useStripe stub whose Payment Sheet methods reject with a
 * clear error. Stripe React Native is native-only; the web subscription
 * flow never calls Payment Sheet (it uses the redirect Checkout path).
 */
import type { ReactNode } from "react";

interface StripeProviderProps {
  publishableKey: string;
  urlScheme?: string;
  merchantIdentifier?: string;
  children: ReactNode;
}

export function StripeProvider({ children }: StripeProviderProps) {
  return <>{children}</>;
}

const WEB_STRIPE_NOT_SUPPORTED = {
  code: "WebNotSupported",
  message: "Stripe Payment Sheet is not available on web.",
  localizedMessage: "Stripe Payment Sheet is not available on web.",
} as const;

export function useStripe() {
  return {
    initPaymentSheet: async () => ({ error: WEB_STRIPE_NOT_SUPPORTED }),
    presentPaymentSheet: async () => ({ error: WEB_STRIPE_NOT_SUPPORTED }),
  };
}
