/**
 * Entitlement API client and types.
 *
 * Matches the backend EntitlementResponse, CreditPackOption,
 * PremiumOption, and PurchaseOptions schemas from app/api/entitlement.py.
 */
import { apiFetch } from "./api";
import { ENTITLEMENT_ENDPOINTS } from "../constants/config";

// ---------------------------------------------------------------------------
// Response types (mirror backend Pydantic models)
// ---------------------------------------------------------------------------

export interface CreditPackOption {
  pack_id: string;
  credits: number;
  price_id: string;
  /** Stripe amount in the smallest currency unit (e.g. cents). */
  amount_cents: number;
  /** ISO 4217 currency code, lowercase (e.g. "usd"). */
  currency: string;
}

export interface PremiumOption {
  price_id: string;
  name: string;
  /** Stripe amount in the smallest currency unit (e.g. cents). */
  amount_cents: number;
  /** ISO 4217 currency code, lowercase (e.g. "usd"). */
  currency: string;
}

export interface PurchaseOptions {
  credit_packs: CreditPackOption[];
  premium: PremiumOption | null;
}

export interface EntitlementState {
  tier: string;
  trial_analyses_remaining: number;
  /** Total trial analyses granted on signup (e.g. 3). */
  trial_analyses_limit: number;
  credit_balance: number;
  can_generate: boolean;
  subscription_status: string | null;
  billing_period_end: string | null;
  purchase_options: PurchaseOptions | null;
}

export interface CheckoutResponse {
  checkout_url: string;
}

export interface CreditPurchaseIntentResponse {
  payment_intent_client_secret: string;
  ephemeral_key: string;
  customer_id: string;
  publishable_key: string;
}

export interface SubscriptionResponse {
  checkout_url: string | null;
  status: string | null;
  message: string | null;
}

export interface CancelSubscriptionResponse {
  status: string;
  message: string;
}

/** Server response status when re-subscribing on an already-active plan. */
export const SUBSCRIPTION_STATUS_ALREADY_SUBSCRIBED = "already_subscribed";

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/** Fetch current user entitlement snapshot (includes purchase_options when can_generate=false). */
export async function fetchEntitlement(): Promise<EntitlementState> {
  return apiFetch<EntitlementState>(ENTITLEMENT_ENDPOINTS.GET);
}

/**
 * Create a Stripe Checkout session for a credit pack purchase.
 *
 * @deprecated Prefer `createCreditPurchaseIntent` — credit packs use the
 * in-app Payment Sheet since PR6. This function is retained for
 * back-compat while older builds remain in the field and will be
 * removed in a follow-up PR.
 */
export async function purchaseCredits(
  creditPackId: string,
): Promise<CheckoutResponse> {
  return apiFetch<CheckoutResponse>(ENTITLEMENT_ENDPOINTS.PURCHASE_CREDITS, {
    method: "POST",
    body: JSON.stringify({
      credit_pack_id: creditPackId,
      success_url: "https://nxme.ai/payment/success",
      cancel_url: "https://nxme.ai/payment/cancel",
    }),
  });
}

/**
 * Create a Stripe PaymentIntent bundle for the in-app Payment Sheet.
 * The returned secrets bootstrap `initPaymentSheet` + `presentPaymentSheet`
 * from `@stripe/stripe-react-native`.
 */
export async function createCreditPurchaseIntent(
  creditPackId: string,
): Promise<CreditPurchaseIntentResponse> {
  return apiFetch<CreditPurchaseIntentResponse>(
    ENTITLEMENT_ENDPOINTS.PURCHASE_CREDITS_INTENT,
    {
      method: "POST",
      body: JSON.stringify({ credit_pack_id: creditPackId }),
    },
  );
}

/** Create a Stripe checkout session for Premium subscription. */
export async function createSubscription(): Promise<SubscriptionResponse> {
  return apiFetch<SubscriptionResponse>(ENTITLEMENT_ENDPOINTS.SUBSCRIBE, {
    method: "POST",
    body: JSON.stringify({
      success_url: "https://nxme.ai/payment/success",
      cancel_url: "https://nxme.ai/payment/cancel",
    }),
  });
}

/** Cancel an active premium subscription (remains active until billing period end). */
export async function cancelSubscription(): Promise<CancelSubscriptionResponse> {
  return apiFetch<CancelSubscriptionResponse>(ENTITLEMENT_ENDPOINTS.SUBSCRIBE, {
    method: "DELETE",
  });
}
