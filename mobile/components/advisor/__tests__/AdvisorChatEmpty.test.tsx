/**
 * AdvisorChatEmpty — renders the scoped title/body and mounts the
 * `ChatSeedChips` row, forwarding chip taps to the caller's
 * `onChipPress` handler.
 *
 * `ChatSeedChips` is mocked to a small surface that fires `onChipPress`
 * with a known text, so the test exercises AdvisorChatEmpty's wiring
 * without the real fetch lifecycle (that lives in ChatSeedChips.test).
 */
import { fireEvent, render } from "@testing-library/react-native";

import { AdvisorChatEmpty } from "../AdvisorChatEmpty";
import {
  ADVISOR_CHAT_EMPTY_BODY,
  ADVISOR_CHAT_EMPTY_TITLE,
} from "../../../constants/config";

// EmptyState pulls in react-native-reanimated via Button; mock the one
// constant we actually consume so Jest doesn't blow up loading worklets.
jest.mock("../../ui/EmptyState", () => ({
  __esModule: true,
  EMPTY_STATE_OPTICAL_LIFT: 96,
}));

jest.mock("../ChatSeedChips", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const ChatSeedChips = ({
    onChipPress,
  }: {
    onChipPress: (text: string) => void;
  }) =>
    ReactMock.createElement(
      RN.Pressable,
      {
        onPress: () => onChipPress("stubbed-seed-text"),
        accessibilityLabel: "mock-chip",
      },
      ReactMock.createElement(RN.Text, null, "chip"),
    );
  return { __esModule: true, ChatSeedChips };
});

jest.mock("../../ui/Text", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Heading = ({ children }: { children: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  const Body = ({ children }: { children: unknown }) =>
    ReactMock.createElement(RN.Text, null, children);
  return { __esModule: true, Body, Heading };
});

describe("AdvisorChatEmpty", () => {
  it("renders the scoped title and body copy", () => {
    const { getByText } = render(<AdvisorChatEmpty onChipPress={jest.fn()} />);
    expect(getByText(ADVISOR_CHAT_EMPTY_TITLE)).toBeTruthy();
    expect(getByText(ADVISOR_CHAT_EMPTY_BODY)).toBeTruthy();
  });

  it("mounts ChatSeedChips and forwards chip presses to onChipPress", () => {
    const onChipPress = jest.fn();
    const { getByLabelText } = render(
      <AdvisorChatEmpty onChipPress={onChipPress} />,
    );
    fireEvent.press(getByLabelText("mock-chip"));
    expect(onChipPress).toHaveBeenCalledWith("stubbed-seed-text");
  });
});
