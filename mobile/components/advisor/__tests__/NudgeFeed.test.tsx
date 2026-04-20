/**
 * NudgeFeed — CTA dispatch tests.
 *
 * Covers:
 *   - NudgeCard receives the correct `index` per render.
 *   - CTA press invokes requestNudgeNextStep + routes to /advisor with seedText.
 *   - 404 response shows the stale-nudge toast and triggers a refresh.
 *   - Generic failure shows the generic-error toast.
 *
 * NudgeCard is mocked to a small surface exposing `ctaFor-${id}` buttons
 * and a visible `index` attribute so we can assert the prop contract
 * without dragging NudgeCard's internals into the test.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { ApiError } from "../../../lib/api";
import { NudgeFeed } from "../NudgeFeed";

// ---------------------------------------------------------------------------
// Mocks — declared before SUT import.
// ---------------------------------------------------------------------------

const mockRouterPush = jest.fn();
jest.mock("expo-router", () => ({
  __esModule: true,
  useRouter: () => ({ push: mockRouterPush }),
}));

const mockShowToast = jest.fn();
jest.mock("../../../lib/toast", () => ({
  __esModule: true,
  showToast: (...args: unknown[]) => mockShowToast(...args),
}));

const mockFetchNudges = jest.fn();
const mockMarkNudgeRead = jest.fn();
const mockRequestNudgeNextStep = jest.fn();
jest.mock("../../../lib/advisor", () => ({
  __esModule: true,
  fetchNudges: (...args: unknown[]) => mockFetchNudges(...args),
  markNudgeRead: (...args: unknown[]) => mockMarkNudgeRead(...args),
  requestNudgeNextStep: (...args: unknown[]) =>
    mockRequestNudgeNextStep(...args),
}));

jest.mock("../../../lib/theme-context", () => ({
  __esModule: true,
  useTheme: () => ({
    theme: {
      accent: "#ff00aa",
      accentMuted: "rgba(255, 0, 170, 0.12)",
      glowShadow: "rgba(255, 0, 170, 0.5)",
    },
  }),
}));

jest.mock("@expo/vector-icons", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Ionicons = ({ name }: { name: string }) =>
    ReactMock.createElement(RN.View, { accessibilityLabel: `icon-${name}` });
  return { __esModule: true, Ionicons };
});

jest.mock("../NudgeDetailSheet", () => {
  const ReactMock = require("react");
  return {
    __esModule: true,
    NudgeDetailSheet: () => ReactMock.createElement(ReactMock.Fragment, null),
  };
});

jest.mock("../AdvisorEmptyOverlay", () => {
  const ReactMock = require("react");
  return {
    __esModule: true,
    AdvisorEmptyOverlay: () =>
      ReactMock.createElement(ReactMock.Fragment, null),
  };
});

jest.mock("../NudgeCard", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const NudgeCard = (props: {
    nudge: { id: string; next_step_label: string };
    index: number;
    onCtaPress?: (
      n: { id: string; next_step_label: string },
    ) => Promise<void> | void;
  }) =>
    ReactMock.createElement(
      RN.Pressable,
      {
        onPress: () => props.onCtaPress?.(props.nudge),
        accessibilityLabel: `ctaFor-${props.nudge.id}`,
        testID: `card-${props.nudge.id}-index-${props.index}`,
      },
      ReactMock.createElement(RN.Text, null, `${props.nudge.id}@${props.index}`),
    );
  return { __esModule: true, NudgeCard };
});

const FIXTURE_NUDGES = [
  {
    id: "n-1",
    body: "body 1",
    next_step_label: "A",
    next_step_seed: "seed-a",
    read_at: null,
    created_at: "2026-04-20T09:00:00Z",
  },
  {
    id: "n-2",
    body: "body 2",
    next_step_label: "B",
    next_step_seed: "seed-b",
    read_at: null,
    created_at: "2026-04-20T08:00:00Z",
  },
] as const;

beforeEach(() => {
  mockRouterPush.mockReset();
  mockShowToast.mockReset();
  mockFetchNudges.mockReset();
  mockRequestNudgeNextStep.mockReset();
  mockFetchNudges.mockResolvedValue({
    nudges: FIXTURE_NUDGES,
    next_cursor: null,
    has_more: false,
  });
});

describe("NudgeFeed", () => {
  it("passes the FlatList index to each NudgeCard", async () => {
    const { getByTestId } = render(<NudgeFeed />);
    await waitFor(() => getByTestId("card-n-1-index-0"));
    expect(getByTestId("card-n-1-index-0")).toBeTruthy();
    expect(getByTestId("card-n-2-index-1")).toBeTruthy();
  });

  it("routes to /advisor with seedText on CTA success", async () => {
    mockRequestNudgeNextStep.mockResolvedValueOnce({ seed_text: "hi ada" });
    const { getByLabelText } = render(<NudgeFeed />);
    await waitFor(() => getByLabelText("ctaFor-n-1"));
    await act(async () => {
      fireEvent.press(getByLabelText("ctaFor-n-1"));
    });
    expect(mockRequestNudgeNextStep).toHaveBeenCalledWith("n-1");
    expect(mockRouterPush).toHaveBeenCalledWith({
      pathname: "/advisor",
      params: { seedText: "hi ada" },
    });
  });

  it("on 404 shows the stale-nudge toast and refreshes the list", async () => {
    mockRequestNudgeNextStep.mockRejectedValueOnce(
      new ApiError(
        404,
        JSON.stringify({ detail: "gone" }),
        "/v1/advisor/nudges/n-1/next-step",
        null,
      ),
    );
    const { getByLabelText } = render(<NudgeFeed />);
    await waitFor(() => getByLabelText("ctaFor-n-1"));
    await act(async () => {
      fireEvent.press(getByLabelText("ctaFor-n-1"));
    });
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "warning" }),
    );
    // Initial fetch + refresh fetch.
    expect(mockFetchNudges).toHaveBeenCalledTimes(2);
    expect(mockRouterPush).not.toHaveBeenCalled();
  });

  it("on generic failure shows the error toast and stays put", async () => {
    mockRequestNudgeNextStep.mockRejectedValueOnce(new Error("boom"));
    const { getByLabelText } = render(<NudgeFeed />);
    await waitFor(() => getByLabelText("ctaFor-n-1"));
    await act(async () => {
      fireEvent.press(getByLabelText("ctaFor-n-1"));
    });
    expect(mockShowToast).toHaveBeenCalledWith(
      expect.objectContaining({ kind: "error" }),
    );
    expect(mockRouterPush).not.toHaveBeenCalled();
  });
});
