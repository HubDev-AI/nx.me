/**
 * useAdvisorComposerLayout — shared layout math for the advisor composers.
 *
 * Chat (ChatView) and Memories (MemoryList) both anchor AdvisorComposer
 * at the bottom of the screen, both need to clear the floating tab bar
 * while it's visible, and both need to drop that offset the moment the
 * keyboard opens (the floating bar hides itself then). The math was
 * copy-pasted between the two; this hook is the single source of truth.
 *
 * `keyboardVerticalOffset` is **measured**, not guessed. The consumer
 * wires `screenAnchorRef` + `onScreenAnchorLayout` to its outermost
 * wrapper `<View>`; the hook calls `measureInWindow` to read the
 * wrapper's absolute screen-Y. That's exactly the distance between
 * the top of the screen and the top of the KeyboardAvoidingView, which
 * is the only reliable value for the KAV offset regardless of what
 * chrome sits above the composer surface (nav header, sub-tab rows,
 * insets). Hand-tuned constants and `useHeaderHeight()` under-count
 * whenever the screen renders additional chrome between the nav header
 * and the KAV (see `docs/notes/keyboard-composer-investigation.md`).
 *
 * Returns:
 *   - `keyboardVerticalOffset` — pass to the surrounding KeyboardAvoidingView.
 *   - `inputBottomPadding` — pass as `bottomPadding` on AdvisorComposer.
 *   - `screenAnchorRef` — attach to the outer `<View>` so we can measure it.
 *   - `onScreenAnchorLayout` — wire to the outer `<View>`'s `onLayout`.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { Keyboard, Platform, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

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
  /** Attach to the outer wrapper `<View>` so the hook can measure its screen-Y. */
  screenAnchorRef: React.RefObject<View | null>;
  /** Wire to the outer wrapper `<View>`'s `onLayout`. */
  onScreenAnchorLayout: () => void;
}

export function useAdvisorComposerLayout(): AdvisorComposerLayout {
  const insets = useSafeAreaInsets();
  const caps = useCapabilities();

  const screenAnchorRef = useRef<View | null>(null);
  const [anchorScreenY, setAnchorScreenY] = useState(0);

  const onScreenAnchorLayout = useCallback(() => {
    // measureInWindow gives absolute screen-space coordinates — immune
    // to every intermediate flex / padding / margin between the wrapper
    // and the screen top. That's the whole point of this hook: the
    // KAV's `keyboardVerticalOffset` must equal the wrapper's absolute
    // screen-Y, and nothing else will compute it correctly in the face
    // of dynamic chrome (nav header + sub-tab rows + insets).
    screenAnchorRef.current?.measureInWindow((_x, y) => {
      if (y >= 0) setAnchorScreenY(y);
    });
  }, []);

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
    // web, KAV needs the measured screen-Y of its top edge.
    keyboardVerticalOffset: Platform.OS === "ios" ? anchorScreenY : 0,
    inputBottomPadding: baseBottomPadding + effectiveTabBarOffset,
    screenAnchorRef,
    onScreenAnchorLayout,
  };
}
