/**
 * Web shim for StripeProvider — renders children only.
 * Stripe React Native is not available on web.
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
