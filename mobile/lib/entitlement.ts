/**
 * Entitlement API client and types.
 *
 * Matches the backend EntitlementResponse and PurchaseOptions schemas
 * from the credits-only payments rebuild (Unit 7 / Unit 12).
 *
 * /v1/entitlement returns the new shape after backend Unit 7 lands.
 */
import { apiFetch } from "./api";
import { ENTITLEMENT_ENDPOINTS } from "../constants/config";

// ---------------------------------------------------------------------------
// Response types (mirror backend Pydantic models)
// ---------------------------------------------------------------------------

/** Pro subscription purchase option returned by the backend. */
export interface ProOption {
  price_id: string;
  amount_cents: number;
  /** ISO 4217 currency code, lowercase (e.g. "usd"). */
  currency: string;
}

export interface PurchaseOptions {
  pro: ProOption;
}

export interface EntitlementState {
  tier: "Free" | "Pro";
  remaining_glowups: number;
  approx_remaining_ada: number;
  subscription_status: "active" | "grace" | "canceled" | "none" | "locked";
  /** ISO datetime string, null when no active subscription. */
  period_end: string | null;
  /** ISO datetime string for grace period end, null when not in grace. */
  grace_end: string | null;
  blocked_reason:
    | "insufficient_credits"
    | "subscription_locked_by_dispute"
    | "none";
  /** UUID of the plan version backing this entitlement. */
  plan_version_id: string;
  purchase_options: PurchaseOptions | null;
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

/** Fetch current user entitlement snapshot. */
export async function fetchEntitlement(): Promise<EntitlementState> {
  return apiFetch<EntitlementState>(ENTITLEMENT_ENDPOINTS.GET);
}

/** Create a Stripe checkout session for Pro subscription. */
export async function createSubscription(): Promise<SubscriptionResponse> {
  return apiFetch<SubscriptionResponse>(ENTITLEMENT_ENDPOINTS.SUBSCRIBE, {
    method: "POST",
    body: JSON.stringify({
      success_url: "https://nxme.ai/payment/success",
      cancel_url: "https://nxme.ai/payment/cancel",
    }),
  });
}

/** Cancel an active Pro subscription (remains active until period_end). */
export async function cancelSubscription(): Promise<CancelSubscriptionResponse> {
  return apiFetch<CancelSubscriptionResponse>(ENTITLEMENT_ENDPOINTS.SUBSCRIBE, {
    method: "DELETE",
  });
}
