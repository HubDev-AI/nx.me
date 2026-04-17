/**
 * AdvisorChatEmpty — chips fire onChipPress with the literal chip text and
 * stay disabled while a send is in flight.
 *
 * Button is mocked so the test runs without react-native-reanimated /
 * worklets initialization (those need a native runtime that jest-expo
 * doesn't ship). The mock preserves the disabled + onPress semantics this
 * component depends on.
 */
import { fireEvent, render } from "@testing-library/react-native";

import { AdvisorChatEmpty } from "../AdvisorChatEmpty";
import {
  ADVISOR_CHAT_EMPTY_BODY,
  ADVISOR_CHAT_EMPTY_TITLE,
  ADVISOR_CHAT_STARTER_CHIPS,
} from "../../../constants/config";

jest.mock("../../ui/Button", () => {
  const ReactMock = require("react");
  const RN = require("react-native");
  const Button = ({
    title,
    onPress,
    disabled,
  }: {
    title: string;
    onPress: () => void;
    disabled?: boolean;
  }) =>
    ReactMock.createElement(
      RN.Pressable,
      {
        onPress: () => {
          if (disabled) return;
          onPress();
        },
        accessibilityRole: "button",
        accessibilityState: { disabled: !!disabled },
        accessibilityLabel: title,
      },
      ReactMock.createElement(RN.Text, null, title),
    );
  return { __esModule: true, Button };
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

  it("renders one chip per ADVISOR_CHAT_STARTER_CHIPS entry", () => {
    const { getByText } = render(<AdvisorChatEmpty onChipPress={jest.fn()} />);
    for (const chip of ADVISOR_CHAT_STARTER_CHIPS) {
      expect(getByText(chip)).toBeTruthy();
    }
  });

  it("invokes onChipPress with the chip text on tap", () => {
    const onChipPress = jest.fn();
    const { getByText } = render(
      <AdvisorChatEmpty onChipPress={onChipPress} />,
    );
    fireEvent.press(getByText(ADVISOR_CHAT_STARTER_CHIPS[0]!));
    expect(onChipPress).toHaveBeenCalledWith(ADVISOR_CHAT_STARTER_CHIPS[0]);
  });

  it("does not invoke onChipPress while isSending is true", () => {
    const onChipPress = jest.fn();
    const { getByText } = render(
      <AdvisorChatEmpty onChipPress={onChipPress} isSending />,
    );
    fireEvent.press(getByText(ADVISOR_CHAT_STARTER_CHIPS[0]!));
    expect(onChipPress).not.toHaveBeenCalled();
  });
});
