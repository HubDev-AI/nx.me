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
 *     Reads the live navigation header height from react-navigation so
 *     the composer lifts correctly on every device (SE → 15 Pro Max,
 *     notch / Dynamic Island / no-notch) without a per-device constant.
 *   - `inputBottomPadding` — pass as `bottomPadding` on AdvisorComposer.
 */
import { useContext, useEffect, useState } from "react";
import { Keyboard, Platform } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { HeaderHeightContext } from "@react-navigation/elements";

import { useCapabilities } from "../lib/capabilities";
import { TAB_BAR_HEIGHT } from "../app/(tabs)/_layout";
import { THEME } from "../constants/theme";

/** The floating tab bar renders whenever at least two tabs are visible. */
const MIN_TABS_FOR_FLOATING_BAR = 2;

export interface AdvisorComposerLayout {
  /** Pass to KeyboardAvoidingView's `keyboardVerticalOffset`. */
  keyboardVerticalOffset: number;
  /** Pass to AdvisorComposer's `bottomPadding` — clears the floating tab bar + home indicator. */
  inputBottomPadding: number;
}

export function useAdvisorComposerLayout(): AdvisorComposerLayout {
  const insets = useSafeAreaInsets();
  const caps = useCapabilities();

  // react-navigation publishes the live header height for the nearest
  // screen through HeaderHeightContext. It includes the platform's top
  // safe-area inset (status bar / notch / Dynamic Island), so the
  // returned value is the exact distance between the top of the
  // KeyboardAvoidingView's layout and the top of the screen — which is
  // precisely the `keyboardVerticalOffset` KAV needs to do its math on
  // any device. When the screen is mounted without a nav header (tests,
  // edge cases), the context is undefined and we fall back to the top
  // safe-area inset.
  const navHeaderHeight = useContext(HeaderHeightContext);
  const topOffset = navHeaderHeight ?? insets.top;

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

  // When the keyboard is open the composer is glued above the keyboard
  // by KAV — the home-indicator / bottom-safe-area padding becomes an
  // unnecessary gap between input and keyboard top. Drop it in that
  // state so the input sits flush. A small design gap stays (`sm`).
  const baseBottomPadding = isKeyboardVisible
    ? THEME.spacing.sm
    : Math.max(insets.bottom, THEME.spacing.sm);

  return {
    // On Android, adjustResize is on by default for Expo projects, so
    // the native layout already shrinks when the keyboard opens — KAV
    // behaviour is "height" and the vertical offset is 0. On iOS and
    // web, KAV handles the lift and needs the top offset to subtract
    // from the keyboard's absolute Y.
    keyboardVerticalOffset: Platform.OS === "ios" ? topOffset : 0,
    inputBottomPadding: baseBottomPadding + effectiveTabBarOffset,
  };
}
