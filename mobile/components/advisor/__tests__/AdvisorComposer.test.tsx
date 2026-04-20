/**
 * AdvisorComposer — prefill-microcopy one-shot behavior tests.
 *
 * Covers:
 *   - Microcopy shows when `initialText` matches `value` on mount.
 *   - Microcopy hides after any character-level divergence.
 *   - Microcopy does NOT re-activate when the user re-types the exact
 *     prefill text (one-shot).
 *   - Microcopy is absent when `initialText` is undefined or empty.
 */
import { useState } from "react";
import { fireEvent, render } from "@testing-library/react-native";

import { AdvisorComposer } from "../AdvisorComposer";
import { COMPOSER_PREFILL_MICROCOPY } from "../../../constants/config";

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

interface HarnessProps {
  initial?: string;
  initialText?: string;
  onRef?: (setValue: (v: string) => void) => void;
}

function Harness({ initial = "", initialText, onRef }: HarnessProps) {
  const [value, setValue] = useState(initial);
  // Expose setValue to the test so we can simulate programmatic prefill
  // setting (what ChatView does via its one-shot useState initializer).
  if (onRef) onRef(setValue);
  return (
    <AdvisorComposer
      value={value}
      onChangeText={setValue}
      onSubmit={() => {}}
      placeholder="Message Ada..."
      accessibilityLabel="Message input"
      submitAccessibilityLabel="Send message"
      initialText={initialText}
    />
  );
}

describe("AdvisorComposer prefill microcopy", () => {
  it("shows microcopy when initialText matches value on mount", () => {
    const seed = "What colour suits me?";
    const { getByText } = render(
      <Harness initial={seed} initialText={seed} />,
    );
    expect(getByText(COMPOSER_PREFILL_MICROCOPY)).toBeTruthy();
  });

  it("does not show microcopy when initialText is empty", () => {
    const { queryByText } = render(<Harness initial="" />);
    expect(queryByText(COMPOSER_PREFILL_MICROCOPY)).toBeNull();
  });

  it("does not show microcopy when initialText differs from value on mount", () => {
    const { queryByText } = render(
      <Harness initial="something else" initialText="the seed" />,
    );
    expect(queryByText(COMPOSER_PREFILL_MICROCOPY)).toBeNull();
  });

  it("dismisses microcopy after the first character-level divergence", () => {
    const seed = "What colour suits me?";
    const { getByText, queryByText, getByLabelText } = render(
      <Harness initial={seed} initialText={seed} />,
    );
    expect(getByText(COMPOSER_PREFILL_MICROCOPY)).toBeTruthy();
    fireEvent.changeText(getByLabelText("Message input"), `${seed}!`);
    expect(queryByText(COMPOSER_PREFILL_MICROCOPY)).toBeNull();
  });

  it("stays dismissed after re-typing the exact prefill text (one-shot)", () => {
    const seed = "What colour suits me?";
    const { queryByText, getByLabelText } = render(
      <Harness initial={seed} initialText={seed} />,
    );
    const input = getByLabelText("Message input");
    fireEvent.changeText(input, `${seed}X`);
    expect(queryByText(COMPOSER_PREFILL_MICROCOPY)).toBeNull();
    // Back to exactly the seed — microcopy must NOT re-activate.
    fireEvent.changeText(input, seed);
    expect(queryByText(COMPOSER_PREFILL_MICROCOPY)).toBeNull();
  });
});
