/**
 * useAdvisorComposerLayout — shared layout math for the advisor composers.
 *
 * Chat (ChatView) and Memories (MemoryList) both anchor AdvisorComposer
 * at the bottom of the screen, both need to clear the floating tab bar
 * while it's visible, and both need to drop that offset the moment the
 * keyboard opens (the floating bar hides itself then). The math was
 * copy-pasted between the two; this hook is the single source of truth.
 *
 * Returns:
 *   - `keyboardVerticalOffset` — pass to the surrounding KeyboardAvoidingView.
 *   - `inputBottomPadding` — pass as `bottomPadding` on AdvisorComposer.
 */
import { useEffect, useState } from "react";
import { Keyboard, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useCapabilities } from "../lib/capabilities";
import { TAB_BAR_HEIGHT } from "../app/(tabs)/_layout";
import { THEME } from "../constants/theme";

/** The floating tab bar renders whenever at least two tabs are visible. */
const MIN_TABS_FOR_FLOATING_BAR = 2;
/** iOS keyboardVerticalOffset used by KeyboardAvoidingView. */
const IOS_KEYBOARD_VERTICAL_OFFSET = 90;

export interface AdvisorComposerLayout {
  /** Pass to KeyboardAvoidingView's `keyboardVerticalOffset`. */
  keyboardVerticalOffset: number;
  /** Pass to AdvisorComposer's `bottomPadding` — clears the floating tab bar + home indicator. */
  inputBottomPadding: number;
}

export function useAdvisorComposerLayout(): AdvisorComposerLayout {
  const insets = useSafeAreaInsets();
  const caps = useCapabilities();

  const visibleTabCount =
    1 /* create */ +
    (caps.canSeeFeed ? 2 : 0) +
    (caps.canUseAdvisor ? 1 : 0);
  const floatingTabBarVisible = visibleTabCount >= MIN_TABS_FOR_FLOATING_BAR;

  const [isKeyboardVisible, setIsKeyboardVisible] = useState(false);
  useEffect(() => {
    const showSub = Keyboard.addListener(
      Platform.OS === "ios" ? "keyboardWillShow" : "keyboardDidShow",
      () => setIsKeyboardVisible(true),
    );
    const hideSub = Keyboard.addListener(
      Platform.OS === "ios" ? "keyboardWillHide" : "keyboardDidHide",
      () => setIsKeyboardVisible(false),
    );
    return () => {
      showSub.remove();
      hideSub.remove();
    };
  }, []);

  const effectiveTabBarOffset =
    floatingTabBarVisible && !isKeyboardVisible ? TAB_BAR_HEIGHT : 0;

  return {
    keyboardVerticalOffset:
      Platform.OS === "ios" ? IOS_KEYBOARD_VERTICAL_OFFSET : 0,
    inputBottomPadding:
      Math.max(insets.bottom, THEME.spacing.sm) + effectiveTabBarOffset,
  };
}
