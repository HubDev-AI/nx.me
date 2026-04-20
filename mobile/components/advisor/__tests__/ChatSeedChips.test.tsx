/**
 * ChatSeedChips — fetch lifecycle, clamping, error paths, and a11y.
 *
 * Covers:
 *   - Happy path: 3 seeds render with their labels.
 *   - Chip press fires `onChipPress(seed.text)` (not `seed.label`).
 *   - Max enforcement: server returns 5 → only first 3 render.
 *   - Empty response → null render (no chip row).
 *   - Network failure → null render, silent (no toast side-effect).
 *   - Timeout (3 s) → null render even if the fetch never resolves.
 *   - Accessibility: chip `accessibilityLabel` matches `seed.text`.
 *
 * The `fetchChatSeeds` export is mocked per-test; no real network.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { ChatSeedChips, LOADING_TIMEOUT_MS } from "../ChatSeedChips";
import type { ChatSeed } from "../../../lib/advisor";

const mockFetchChatSeeds = jest.fn();
jest.mock("../../../lib/advisor", () => ({
  __esModule: true,
  fetchChatSeeds: (...args: unknown[]) => mockFetchChatSeeds(...args),
}));

function makeSeeds(n: number): ChatSeed[] {
  return Array.from({ length: n }, (_, i) => ({
    label: `L${i}`,
    text: `full seed text ${i}`,
  }));
}

beforeEach(() => {
  mockFetchChatSeeds.mockReset();
});

describe("ChatSeedChips", () => {
  it("renders 3 chips with their labels on happy path", async () => {
    mockFetchChatSeeds.mockResolvedValueOnce({ seeds: makeSeeds(3) });
    const { getByText } = render(<ChatSeedChips onChipPress={jest.fn()} />);
    await waitFor(() => getByText("L0"));
    expect(getByText("L0")).toBeTruthy();
    expect(getByText("L1")).toBeTruthy();
    expect(getByText("L2")).toBeTruthy();
  });

  it("calls onChipPress with seed.text (full prompt), not seed.label", async () => {
    mockFetchChatSeeds.mockResolvedValueOnce({ seeds: makeSeeds(1) });
    const onChipPress = jest.fn();
    const { getByText } = render(<ChatSeedChips onChipPress={onChipPress} />);
    await waitFor(() => getByText("L0"));
    fireEvent.press(getByText("L0"));
    expect(onChipPress).toHaveBeenCalledWith("full seed text 0");
    expect(onChipPress).not.toHaveBeenCalledWith("L0");
  });

  it("clamps to the first 3 seeds when the server returns 5", async () => {
    mockFetchChatSeeds.mockResolvedValueOnce({ seeds: makeSeeds(5) });
    const { getByText, queryByText } = render(
      <ChatSeedChips onChipPress={jest.fn()} />,
    );
    await waitFor(() => getByText("L0"));
    expect(getByText("L0")).toBeTruthy();
    expect(getByText("L1")).toBeTruthy();
    expect(getByText("L2")).toBeTruthy();
    expect(queryByText("L3")).toBeNull();
    expect(queryByText("L4")).toBeNull();
  });

  it("renders nothing when the server returns an empty seeds array", async () => {
    mockFetchChatSeeds.mockResolvedValueOnce({ seeds: [] });
    const { queryByLabelText } = render(
      <ChatSeedChips onChipPress={jest.fn()} />,
    );
    // Give the promise chain a tick to resolve.
    await act(async () => {
      await Promise.resolve();
    });
    // No real or mock chip should be queryable.
    expect(queryByLabelText(/seed/i)).toBeNull();
  });

  it("renders nothing on network failure (silent)", async () => {
    mockFetchChatSeeds.mockRejectedValueOnce(new Error("boom"));
    const { queryByLabelText } = render(
      <ChatSeedChips onChipPress={jest.fn()} />,
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(queryByLabelText(/seed/i)).toBeNull();
  });

  it("renders nothing when the fetch exceeds the skeleton timeout", async () => {
    jest.useFakeTimers();
    // Fetch that never resolves — forces the timeout branch.
    mockFetchChatSeeds.mockImplementationOnce(
      () => new Promise(() => {}),
    );
    const { queryByLabelText } = render(
      <ChatSeedChips onChipPress={jest.fn()} />,
    );
    await act(async () => {
      jest.advanceTimersByTime(LOADING_TIMEOUT_MS);
    });
    expect(queryByLabelText(/seed/i)).toBeNull();
    jest.useRealTimers();
  });

  it("sets accessibilityLabel to seed.text (not seed.label) for VoiceOver", async () => {
    mockFetchChatSeeds.mockResolvedValueOnce({ seeds: makeSeeds(2) });
    const { getByLabelText, queryByLabelText } = render(
      <ChatSeedChips onChipPress={jest.fn()} />,
    );
    await waitFor(() => getByLabelText("full seed text 0"));
    expect(getByLabelText("full seed text 0")).toBeTruthy();
    expect(getByLabelText("full seed text 1")).toBeTruthy();
    // The short label is NOT the a11y label.
    expect(queryByLabelText("L0")).toBeNull();
  });
});
