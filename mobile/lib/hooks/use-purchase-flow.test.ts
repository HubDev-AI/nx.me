import { act, renderHook, waitFor } from "@testing-library/react-native";

import { usePurchaseFlow } from "./use-purchase-flow";

const mockInitPaymentSheet = jest.fn();
const mockPresentPaymentSheet = jest.fn();
const mockCreateIntent = jest.fn();
const mockFetchEntitlement = jest.fn();
const mockShowToast = jest.fn();

jest.mock("../stripe-web-shim", () => ({
  useStripe: () => ({
    initPaymentSheet: mockInitPaymentSheet,
    presentPaymentSheet: mockPresentPaymentSheet,
  }),
}));

jest.mock("../entitlement", () => ({
  createCreditPurchaseIntent: (...args: unknown[]) => mockCreateIntent(...args),
  fetchEntitlement: (...args: unknown[]) => mockFetchEntitlement(...args),
  createSubscription: jest.fn(),
  cancelSubscription: jest.fn(),
  SUBSCRIPTION_STATUS_ALREADY_SUBSCRIBED: "already_subscribed",
}));

jest.mock("../errors", () => ({
  parseApiError: (err: unknown) => ({
    message: err instanceof Error ? err.message : "error",
  }),
}));

jest.mock("../toast", () => ({
  showToast: (...args: unknown[]) => mockShowToast(...args),
}));

const PACK = {
  pack_id: "10_credits",
  credits: 10,
  price_id: "price_10",
  amount_cents: 499,
  currency: "usd",
};

const ENTITLEMENT = {
  tier: "TRIAL",
  trial_analyses_remaining: 0,
  trial_analyses_limit: 2,
  credit_balance: 10,
  can_generate: true,
  subscription_status: null,
  billing_period_end: null,
  purchase_options: null,
};

beforeEach(() => {
  mockInitPaymentSheet.mockReset();
  mockPresentPaymentSheet.mockReset();
  mockCreateIntent.mockReset();
  mockFetchEntitlement.mockReset();
  mockShowToast.mockReset();

  mockFetchEntitlement.mockResolvedValue(ENTITLEMENT);
  mockCreateIntent.mockResolvedValue({
    payment_intent_client_secret: "pi_1_secret",
    ephemeral_key: "ek_1",
    customer_id: "cus_1",
    // Matches STRIPE_PUBLISHABLE_KEY from jest.setup.ts (empty string) so
    // the dev-only mismatch warn stays quiet in unit tests.
    publishable_key: "",
  });
});

describe("usePurchaseFlow.buyCredits", () => {
  it("inits + presents Payment Sheet and refetches entitlement on success", async () => {
    mockInitPaymentSheet.mockResolvedValue({});
    mockPresentPaymentSheet.mockResolvedValue({});

    const { result } = renderHook(() =>
      usePurchaseFlow({ autoLoad: false }),
    );

    await act(async () => {
      await result.current.buyCredits(PACK);
    });

    expect(mockCreateIntent).toHaveBeenCalledWith("10_credits");
    expect(mockInitPaymentSheet).toHaveBeenCalledWith(
      expect.objectContaining({
        paymentIntentClientSecret: "pi_1_secret",
        customerId: "cus_1",
        customerEphemeralKeySecret: "ek_1",
      }),
    );
    expect(mockPresentPaymentSheet).toHaveBeenCalled();
    expect(mockFetchEntitlement).toHaveBeenCalled();
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "success" }),
    );
  });

  it("silently no-ops when user cancels the sheet", async () => {
    mockInitPaymentSheet.mockResolvedValue({});
    mockPresentPaymentSheet.mockResolvedValue({
      error: { code: "Canceled", message: "user canceled" },
    });

    const { result } = renderHook(() =>
      usePurchaseFlow({ autoLoad: false }),
    );

    await act(async () => {
      await result.current.buyCredits(PACK);
    });

    expect(mockPresentPaymentSheet).toHaveBeenCalled();
    expect(mockFetchEntitlement).not.toHaveBeenCalled();
    expect(mockShowToast).not.toHaveBeenCalled();
    await waitFor(() => expect(result.current.purchasingId).toBeNull());
  });

  it("surfaces an error toast on init failure", async () => {
    mockInitPaymentSheet.mockResolvedValue({
      error: { code: "Failed", message: "init failed" },
    });

    const { result } = renderHook(() =>
      usePurchaseFlow({ autoLoad: false }),
    );

    await act(async () => {
      await result.current.buyCredits(PACK);
    });

    expect(mockPresentPaymentSheet).not.toHaveBeenCalled();
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error", message: "init failed" }),
    );
  });
});
