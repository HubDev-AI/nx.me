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
}

export interface PremiumOption {
  price_id: string;
  name: string;
}

export interface PurchaseOptions {
  credit_packs: CreditPackOption[];
  premium: PremiumOption | null;
}

export interface EntitlementState {
  tier: string;
  trial_analyses_remaining: number;
  credit_balance: number;
  can_generate: boolean;
  subscription_status: string | null;
  billing_period_end: string | null;
  purchase_options: PurchaseOptions | null;
}

export interface CheckoutResponse {
  checkout_url: string;
}

export interface SubscriptionResponse {
  checkout_url: string | null;
  status: string | null;
  message: string | null;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/** Fetch current user entitlement snapshot (includes purchase_options when can_generate=false). */
export async function fetchEntitlement(): Promise<EntitlementState> {
  return apiFetch<EntitlementState>(ENTITLEMENT_ENDPOINTS.GET);
}

/** Create a Stripe checkout session for a credit pack purchase. */
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
