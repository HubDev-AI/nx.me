/**
 * ZoomableImageModal — full-screen image viewer with pinch-zoom,
 * pan (when zoomed), double-tap reset, and swipe-down-to-dismiss.
 *
 * Built on React Native's `Modal` + `PanResponder` + Reanimated shared
 * values — deliberately avoids `react-native-gesture-handler` so the
 * project doesn't take on a native dep for a single viewer.
 *
 * Exports a handful of pure helpers used by the gesture math so they
 * can be tested without mounting the component (jest-expo can't mount
 * Reanimated reliably).
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Modal,
  PanResponder,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import Animated, {
  useAnimatedStyle,
  useSharedValue,
  withSpring,
  withTiming,
} from "react-native-reanimated";
import { StatusBar } from "expo-status-bar";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { HeaderBackButton, HeaderBackButtonSpacer } from "./HeaderBackButton";
import { Heading } from "./Text";
import {
  clampScale,
  shouldDismissOnSwipeDown,
  twoFingerDistance,
} from "./zoomable-image-math";

// ---------------------------------------------------------------------------
// Constants — local (math constants live in zoomable-image-math.ts)
// ---------------------------------------------------------------------------

/** Max gap (ms) between two taps for them to count as a double-tap. */
const DOUBLE_TAP_MS = 280;

const RESET_SPRING = { damping: 22, stiffness: 240, mass: 1 } as const;
const DISMISS_TIMING = { duration: 180 } as const;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface ZoomableImageModalProps {
  visible: boolean;
  sourceUri: string | null;
  altText: string;
  onClose: () => void;
}

export function ZoomableImageModal({
  visible,
  sourceUri,
  altText,
  onClose,
}: ZoomableImageModalProps) {
  const { width: winW, height: winH } = useWindowDimensions();
  // SafeAreaView sometimes reports insets=0 on the first frame when
  // presented inside a Modal with `statusBarTranslucent`, which made
  // the header look missing on the first open. Reading the insets
  // explicitly keeps the header visible on mount #1.
  const insets = useSafeAreaInsets();

  const scale = useSharedValue(1);
  const translateX = useSharedValue(0);
  const translateY = useSharedValue(0);

  const pinchStartDistance = useRef<number>(0);
  const pinchStartScale = useRef<number>(1);
  const panStartX = useRef<number>(0);
  const panStartY = useRef<number>(0);
  const lastTapAt = useRef<number>(0);

  // Reset shared values whenever the modal re-opens so successive opens
  // start from a clean zoom state.
  useEffect(() => {
    if (visible) {
      scale.value = 1;
      translateX.value = 0;
      translateY.value = 0;
      pinchStartDistance.current = 0;
      pinchStartScale.current = 1;
      lastTapAt.current = 0;
    }
  }, [visible, scale, translateX, translateY]);

  const reset = useCallback(() => {
    scale.value = withSpring(1, RESET_SPRING);
    translateX.value = withSpring(0, RESET_SPRING);
    translateY.value = withSpring(0, RESET_SPRING);
  }, [scale, translateX, translateY]);

  const dismiss = useCallback(() => {
    // Slide the image down a touch while fading via the parent Modal's
    // built-in fade; onClose triggers the Modal unmount.
    translateY.value = withTiming(winH, DISMISS_TIMING, () => {});
    onClose();
  }, [onClose, translateY, winH]);

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: (evt) => {
          const now = Date.now();
          const touches = evt.nativeEvent.touches;
          pinchStartDistance.current = twoFingerDistance(touches);
          pinchStartScale.current = scale.value;
          panStartX.current = translateX.value;
          panStartY.current = translateY.value;

          // Double-tap detection — second tap within window resets.
          if (touches.length === 1) {
            if (now - lastTapAt.current < DOUBLE_TAP_MS) {
              reset();
              lastTapAt.current = 0;
              return;
            }
            lastTapAt.current = now;
          } else {
            // Multi-touch cancels any pending double-tap window.
            lastTapAt.current = 0;
          }
        },
        onPanResponderMove: (evt, gs) => {
          const touches = evt.nativeEvent.touches;

          if (touches.length >= 2) {
            // Re-seed whenever the pinch transitions in (first Move
            // frame of a 2-finger span). pinchStartDistance is cleared
            // both on release AND on 2→1 transitions below, so every
            // fresh 2-finger span re-seeds from the current spread —
            // no cross-span scale jump after a 2→1→2 lift/re-pinch.
            if (pinchStartDistance.current === 0) {
              pinchStartDistance.current = twoFingerDistance(touches);
              pinchStartScale.current = scale.value;
            }
            const d = twoFingerDistance(touches);
            if (pinchStartDistance.current > 0 && d > 0) {
              const next = clampScale(
                pinchStartScale.current * (d / pinchStartDistance.current),
              );
              scale.value = next;
            }
            return;
          }

          // <2 touches — clear the pinch seeds so the next 2-finger
          // span re-seeds from the new spread (see 2+ branch above).
          // Also re-anchor the pan origin to the current translate so
          // a pan that follows a pinch doesn't jump.
          if (pinchStartDistance.current !== 0) {
            pinchStartDistance.current = 0;
            panStartX.current = translateX.value - gs.dx;
            panStartY.current = translateY.value - gs.dy;
          }

          // Single-finger — either pan (when zoomed) or track the
          // drag for swipe-down dismiss.
          translateX.value = panStartX.current + gs.dx;
          translateY.value = panStartY.current + gs.dy;
        },
        onPanResponderRelease: (_evt, gs) => {
          // Reset the pinch seeds so the next pinch starts fresh.
          pinchStartDistance.current = 0;

          // Swipe-down dismiss only when the image is at rest (scale 1).
          if (scale.value <= 1) {
            if (shouldDismissOnSwipeDown(translateY.value, gs.vy)) {
              dismiss();
              return;
            }
            // Not dismissing — settle back.
            translateX.value = withSpring(0, RESET_SPRING);
            translateY.value = withSpring(0, RESET_SPRING);
          }
        },
        onPanResponderTerminationRequest: () => false,
      }),
    [dismiss, reset, scale, translateX, translateY],
  );

  const imageStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: translateX.value },
      { translateY: translateY.value },
      { scale: scale.value },
    ],
  }));

  if (!sourceUri) return null;

  return (
    <Modal
      visible={visible}
      onRequestClose={onClose}
      animationType="fade"
      presentationStyle="overFullScreen"
      transparent
      statusBarTranslucent
    >
      <StatusBar style="light" />
      <View style={styles.backdrop}>
        {/* Image area fills the FULL backdrop (not "backdrop minus
            header") so the image is centered against the whole
            viewport. Anchoring it to the flex column below the header
            row pushed the image down by ~headerHeight/2 — the user
            saw the photo sitting visibly below screen-center. The
            header renders on top via absolute positioning instead. */}
        <View
          style={styles.imageArea}
          accessibilityLabel={`${altText}, enlarged view`}
          accessibilityRole="image"
          {...panResponder.panHandlers}
        >
          <Animated.Image
            source={{ uri: sourceUri }}
            style={[
              styles.image,
              { width: winW, height: winH },
              imageStyle,
            ]}
            resizeMode="contain"
          />
        </View>
        {/* pointerEvents="box-none" so taps on the title text or
            spacer fall through to the imageArea's panResponder. The
            close-button Pressable still captures its own touches. */}
        <View
          style={[styles.headerRow, { paddingTop: insets.top }]}
          pointerEvents="box-none"
        >
          <HeaderBackButton
            onPress={onClose}
            tintColor={THEME.colors.white}
            accessibilityLabel="Close image viewer"
          />
          <Heading
            size="md"
            color={THEME.colors.white}
            style={styles.headerTitle}
            numberOfLines={1}
            maxFontSizeMultiplier={1.3}
          >
            {altText}
          </Heading>
          <HeaderBackButtonSpacer />
        </View>
      </View>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const HEADER_TITLE_FONT_SIZE = 20;

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "#000",
  },
  // Mirrors the Upload / Result header row — Back button left, Heading
  // size="md" centered, spacer right. paddingTop is applied at the
  // call site so useSafeAreaInsets can survive a Modal remount.
  // Absolute-positioned so it overlays the imageArea instead of
  // pushing it down — the image must center against the full screen
  // viewport, not against "screen minus header".
  headerRow: {
    position: "absolute",
    top: 0,
    left: 0,
    right: 0,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: THEME.spacing.sm,
    paddingBottom: THEME.spacing.sm,
  },
  headerTitle: {
    fontSize: HEADER_TITLE_FONT_SIZE,
  },
  // absoluteFill so the image-centering box equals the full backdrop
  // (the entire screen). With contain + width:winW + height:winH, the
  // image's bounding box is the full viewport and resizeMode centers
  // the picture inside it — landing the photo at exact screen-center.
  imageArea: {
    ...StyleSheet.absoluteFillObject,
    alignItems: "center",
    justifyContent: "center",
  },
  image: {
    alignSelf: "center",
  },
});
