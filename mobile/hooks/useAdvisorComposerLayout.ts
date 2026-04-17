/**
 * useAdvisorComposerLayout — shared bottom-padding math for advisor composers.
 *
 * Chat (ChatView) and Memories (MemoryList) both anchor AdvisorComposer
 * at the bottom of the screen and both need the composer to clear the
 * floating tab bar + home indicator while the keyboard is down, then
 * drop that gap when the keyboard opens (the floating bar hides and the
 * composer is lifted flush against the keyboard by KeyboardStickyView
 * inside AdvisorComposer).
 *
 * Returns:
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

export interface AdvisorComposerLayout {
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

  // When the keyboard is open the composer is translated flush against
  // the keyboard top by KeyboardStickyView — the home-indicator /
  // bottom-safe-area padding becomes dead space between input and
  // keyboard. Drop it in that state; keep a small design gap.
  const baseBottomPadding = isKeyboardVisible
    ? THEME.spacing.sm
    : Math.max(insets.bottom, THEME.spacing.sm);

  return {
    inputBottomPadding: baseBottomPadding + effectiveTabBarOffset,
  };
}
