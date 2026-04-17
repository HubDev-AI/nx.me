/**
 * useRefundToast — fires once per (jobId, device) when credit_refunded
 * flips true; suppressed but still marked-seen on /(auth) routes.
 */
import { renderHook, waitFor } from "@testing-library/react-native";

import AsyncStorage from "@react-native-async-storage/async-storage";

import {
  REFUND_TOAST_CANCELLED,
  REFUND_TOAST_FAILED,
} from "../../../constants/config";
import type { JobResult } from "../../analysis";
import { useRefundToast } from "../use-refund-toast";
import {
  __resetRefundToastSeenForTests,
  hasSeenRefundToastSync,
  loadRefundToastSeen,
} from "../../refund-toast-store";

const mockShowToast = jest.fn();
jest.mock("../../toast", () => ({
  __esModule: true,
  showToast: (...args: unknown[]) => mockShowToast(...args),
}));

let mockPathname = "/(tabs)/profile";
jest.mock("expo-router", () => ({
  __esModule: true,
  usePathname: () => mockPathname,
}));

jest.mock("@react-native-async-storage/async-storage", () => {
  const store = new Map<string, string>();
  return {
    __esModule: true,
    default: {
      getItem: jest.fn(async (key: string) => store.get(key) ?? null),
      setItem: jest.fn(async (key: string, value: string) => {
        store.set(key, value);
      }),
      removeItem: jest.fn(async () => {}),
      clear: jest.fn(async () => {
        store.clear();
      }),
    },
  };
});

function makeJob(overrides: Partial<JobResult> = {}): JobResult {
  return {
    job_id: "job-1",
    status: "failed",
    estimated_wait_seconds: null,
    elapsed_seconds: null,
    before_image_url: null,
    after_image_url: null,
    identity_preserved: null,
    failure_reason: null,
    credit_refunded: true,
    retry_eligible: null,
    user_guidance: null,
    ...overrides,
  };
}

describe("useRefundToast", () => {
  beforeEach(async () => {
    mockShowToast.mockReset();
    mockPathname = "/(tabs)/profile";
    // The AsyncStorage mock persists across tests — clear it before
    // re-hydrating so the seen-set starts empty for each case.
    await AsyncStorage.clear();
    __resetRefundToastSeenForTests();
    await loadRefundToastSeen();
  });

  it("no-op when credit_refunded is null", () => {
    const job = makeJob({ credit_refunded: null });
    renderHook(() => useRefundToast(job));
    expect(mockShowToast).not.toHaveBeenCalled();
  });

  it("no-op when credit_refunded is false", () => {
    const job = makeJob({ credit_refunded: false });
    renderHook(() => useRefundToast(job));
    expect(mockShowToast).not.toHaveBeenCalled();
  });

  it("fires success toast with failed copy when credit_refunded=true and status=failed", () => {
    const job = makeJob({ status: "failed" });
    renderHook(() => useRefundToast(job));
    expect(mockShowToast).toHaveBeenCalledWith({
      kind: "success",
      message: REFUND_TOAST_FAILED,
    });
  });

  it("fires success toast with cancelled copy when status=cancelled", () => {
    const job = makeJob({ status: "cancelled" });
    renderHook(() => useRefundToast(job));
    expect(mockShowToast).toHaveBeenCalledWith({
      kind: "success",
      message: REFUND_TOAST_CANCELLED,
    });
  });

  it("dedupe: a second hook for the same jobId does not re-fire", () => {
    const job = makeJob();
    renderHook(() => useRefundToast(job));
    renderHook(() => useRefundToast(job));
    expect(mockShowToast).toHaveBeenCalledTimes(1);
  });

  it("suppresses toast on /(auth) route but still marks seen", async () => {
    mockPathname = "/(auth)/login";
    const job = makeJob();
    renderHook(() => useRefundToast(job));
    expect(mockShowToast).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(hasSeenRefundToastSync("job-1")).toBe(true);
    });
  });

  it("does not re-fire after a /(auth)-suppressed seen marker", () => {
    mockPathname = "/(auth)/login";
    const job = makeJob();
    renderHook(() => useRefundToast(job));
    mockPathname = "/(tabs)/profile";
    renderHook(() => useRefundToast(job));
    expect(mockShowToast).not.toHaveBeenCalled();
  });

  it("does not re-fire on cold start when AsyncStorage already has the jobId seen", async () => {
    // Simulate a prior launch having seen this jobId — persist the
    // marker, then start a fresh in-memory cache so the hook has to
    // hydrate before deciding.
    await AsyncStorage.setItem(
      "@nxme:refund_toasts_seen",
      JSON.stringify(["job-1"]),
    );
    __resetRefundToastSeenForTests();

    const job = makeJob({ job_id: "job-1" });
    const { rerender } = renderHook((props: JobResult) => useRefundToast(props), {
      initialProps: job,
    });
    // Wait for hydration — without the hydrated gate, the toast
    // would have already fired by now.
    await waitFor(() => {
      expect(hasSeenRefundToastSync("job-1")).toBe(true);
    });
    rerender(job);
    expect(mockShowToast).not.toHaveBeenCalled();
  });
});
