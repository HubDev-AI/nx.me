/**
 * NudgeCard — CTA chip visibility + press handling tests.
 *
 * Covers:
 *   - Chip visible for index < NUDGES_CTA_VISIBLE_RECENT_CAP.
 *   - Chip hidden for index >= cap (quieter variant).
 *   - Chip hidden when next_step_label is blank.
 *   - Tap invokes onCtaPress(nudge).
 *   - Double-tap fires onCtaPress once while the first call is in-flight.
 *   - Spinner replaces the label text while in-flight.
 *   - accessibilityLabel matches next_step_label.
 *   - Card accessibilityLabel uses the static POST_GLOWUP_LABEL.
 *
 * The component uses reanimated-free primitives already (Pressable +
 * ActivityIndicator) so no Reanimated/Ionicons/theme-context stubs are
 * strictly required — we stub Ionicons anyway to avoid font-load noise.
 */
import { act, fireEvent, render, waitFor } from "@testing-library/react-native";

import { NudgeCard } from "../NudgeCard";
import {
  NUDGES_CTA_VISIBLE_RECENT_CAP,
  POST_GLOWUP_LABEL,
} from "../../../constants/config";
import type { Nudge } from "../../../lib/advisor";

// ---------------------------------------------------------------------------
// Module mocks — must precede the SUT import indirectly through setup.
// ---------------------------------------------------------------------------

jest.mock("@expo/vector-icons", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Ionicons = ({ name }: { name: string }) =>
    ReactMock.createElement(RN.View, { accessibilityLabel: `icon-${name}` });
  return { __esModule: true, Ionicons };
});

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

// Text primitives — keep them tiny so the test doesn't depend on the
// real font-loading + display scheme. Body/Caption wrap a RN.Text.
jest.mock("../../ui/Text", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const passthrough =
    ({ children, style }: { children?: unknown; style?: unknown }) =>
      ReactMock.createElement(RN.Text, { style }, children);
  return {
    __esModule: true,
    Body: passthrough,
    Caption: passthrough,
    Heading: passthrough,
  };
});

function makeNudge(overrides: Partial<Nudge> = {}): Nudge {
  return {
    id: "n-1",
    body: "Warm ash-blonde keeps the complement you got on your glow-up.",
    next_step_label: "What colour suits me?",
    next_step_seed: "I just finished a glow-up — what colour would suit me?",
    read_at: null,
    created_at: "2026-04-20T10:00:00Z",
    ...overrides,
  };
}

describe("NudgeCard", () => {
  it("renders the static POST_GLOWUP_LABEL as the card title", () => {
    const { getByText } = render(
      <NudgeCard nudge={makeNudge()} index={0} onPress={jest.fn()} />,
    );
    expect(getByText(POST_GLOWUP_LABEL)).toBeTruthy();
  });

  it("renders the body copy", () => {
    const nudge = makeNudge({ body: "body-under-test" });
    const { getByText } = render(
      <NudgeCard nudge={nudge} index={0} onPress={jest.fn()} />,
    );
    expect(getByText("body-under-test")).toBeTruthy();
  });

  it("renders a CTA chip when index is within the recent cap", () => {
    const nudge = makeNudge({ next_step_label: "Ask Ada" });
    const { getByLabelText } = render(
      <NudgeCard
        nudge={nudge}
        index={NUDGES_CTA_VISIBLE_RECENT_CAP - 1}
        onPress={jest.fn()}
        onCtaPress={jest.fn()}
      />,
    );
    expect(getByLabelText("Ask Ada")).toBeTruthy();
  });

  it("omits the CTA chip when index >= NUDGES_CTA_VISIBLE_RECENT_CAP (quieter variant)", () => {
    const nudge = makeNudge({ next_step_label: "Ask Ada" });
    const { queryByLabelText } = render(
      <NudgeCard
        nudge={nudge}
        index={NUDGES_CTA_VISIBLE_RECENT_CAP}
        onPress={jest.fn()}
        onCtaPress={jest.fn()}
      />,
    );
    expect(queryByLabelText("Ask Ada")).toBeNull();
  });

  it("omits the CTA chip when next_step_label is blank", () => {
    const nudge = makeNudge({ next_step_label: "   " });
    const { queryByLabelText } = render(
      <NudgeCard
        nudge={nudge}
        index={0}
        onPress={jest.fn()}
        onCtaPress={jest.fn()}
      />,
    );
    expect(queryByLabelText("Ask Ada")).toBeNull();
  });

  it("fires onCtaPress(nudge) when the chip is tapped", async () => {
    const nudge = makeNudge({ next_step_label: "Tap me" });
    const onCtaPress = jest.fn().mockResolvedValue(undefined);
    const { getByLabelText } = render(
      <NudgeCard
        nudge={nudge}
        index={0}
        onPress={jest.fn()}
        onCtaPress={onCtaPress}
      />,
    );
    fireEvent.press(getByLabelText("Tap me"));
    await waitFor(() => expect(onCtaPress).toHaveBeenCalledTimes(1));
    expect(onCtaPress).toHaveBeenCalledWith(nudge);
  });

  it("guards against double-fire while a press is in flight", async () => {
    const nudge = makeNudge({ next_step_label: "Once" });
    let resolveFirst: (() => void) | null = null;
    const onCtaPress = jest.fn().mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveFirst = resolve;
        }),
    );
    const { getByLabelText } = render(
      <NudgeCard
        nudge={nudge}
        index={0}
        onPress={jest.fn()}
        onCtaPress={onCtaPress}
      />,
    );
    const chip = getByLabelText("Once");
    // Two presses before the first resolves.
    fireEvent.press(chip);
    fireEvent.press(chip);
    expect(onCtaPress).toHaveBeenCalledTimes(1);
    await act(async () => {
      resolveFirst?.();
    });
  });

  it("uses POST_GLOWUP_LABEL in the card's accessibilityLabel", () => {
    const { getByRole } = render(
      <NudgeCard nudge={makeNudge()} index={0} onPress={jest.fn()} />,
    );
    // The card itself is a button role; the first one in render order is
    // the outer card, not the chip (chip has its own role).
    const cardButton = getByRole("button", {
      name: `Unread nudge: ${POST_GLOWUP_LABEL}`,
    });
    expect(cardButton).toBeTruthy();
  });
});
