/**
 * BeforeAfterSlider — draggable split-view comparison slider.
 *
 * Entrance: spring from 0 → initialSplit on mount (~600ms).
 * Interaction: PanResponder drag + tap-to-jump. Tap anywhere on the slider
 *   and the divider springs to that x position; dragging then continues
 *   from the new position.
 * Accessibility: VoiceOver custom action fires onAccessibilityToggle.
 * Brand: glow-ring handle uses session accent colour from useTheme().
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Image,
  PanResponder,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import Animated, {
  clamp,
  runOnJS,
  useAnimatedStyle,
  useSharedValue,
  withSpring,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { hapticLight } from "../../lib/haptics";
import { Label } from "../ui/Text";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/**
 * Total horizontal padding reserved around the slider (sum of left + right).
 * Matches the page padding in upload/result screens so the slider aligns
 * with surrounding content.
 */
const TOTAL_H_PADDING = THEME.spacing.xl * 2;

/** Aspect ratio: portrait 3:4 (same as existing image cards). */
const ASPECT_RATIO_H_OVER_W = 4 / 3;

/** Width of the draggable divider line (bumped from 2 → 3 for visibility). */
const DIVIDER_WIDTH = 3;

/** Diameter of the circular drag handle. */
const HANDLE_SIZE = 36;

/** Thickness of the glow-ring on the handle (brand accent). */
const GLOW_RING_WIDTH = 2;

/** Extra touch area around the handle so the divider is easy to grab. */
const HANDLE_HIT_PADDING = 24;

/**
 * Minimum horizontal-dominance (in px) a move must clear before the
 * slider claims the gesture. Below this, the parent ScrollView keeps
 * the drag — so vertical scrolls pass through cleanly.
 */
const DIRECTION_THRESHOLD_PX = 10;

/** Spring config for entrance + accessibility-toggle animations. */
const ENTRANCE_SPRING = {
  damping: 15,
  stiffness: 150,
  mass: 1,
} as const;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BeforeAfterSliderProps {
  beforeUrl: string;
  afterUrl: string;
  /** e.g. "Glow Up" for this feature, "Clean Girl · Dewy" for Makeup. */
  rightLabel: string;
  /** Default split position (0–1). Default 1.0 — glow-up visible, user drags left to reveal before. */
  initialSplit?: number;
  /** Called by VoiceOver accessibility action (toggles between 0.25 and 0.75). */
  onAccessibilityToggle?: () => void;
  /**
   * Pure-tap callback — fires when the user taps the before side of
   * the image (to the right of the current divider) without dragging.
   * Parent typically opens a zoomable full-screen view.
   */
  onPressBeforeImage?: () => void;
  /**
   * Pure-tap callback — fires when the user taps the glow-up side of
   * the image (to the left of the current divider) without dragging.
   */
  onPressAfterImage?: () => void;
}

/** Max combined travel (px) a release can show and still count as a tap. */
const TAP_MAX_TRAVEL_PX = 8;

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BeforeAfterSlider({
  beforeUrl,
  afterUrl,
  rightLabel,
  initialSplit = 1.0,
  onAccessibilityToggle,
  onPressBeforeImage,
  onPressAfterImage,
}: BeforeAfterSliderProps) {
  const { theme } = useTheme();
  const { width: windowWidth } = useWindowDimensions();
  const sliderWidth = windowWidth - TOTAL_H_PADDING;
  const sliderHeight = sliderWidth * ASPECT_RATIO_H_OVER_W;

  const splitPosition = useSharedValue(0);
  const gestureStartSplit = useRef(0);
  // Track gesture origin so release can distinguish tap (no travel) from
  // drag. Set in onPanResponderGrant; read in onPanResponderRelease.
  const gestureStartX = useRef(0);

  // Kick off entrance animation once after mount. Reanimated shared-value
  // writes during render are not safe under concurrent rendering.
  useEffect(() => {
    splitPosition.value = withSpring(initialSplit, ENTRANCE_SPRING);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAccessibilityToggle = useCallback(() => {
    const current = splitPosition.value;
    splitPosition.value = withSpring(
      current > 0.5 ? 0.25 : 0.75,
      ENTRANCE_SPRING,
    );
    onAccessibilityToggle?.();
  }, [splitPosition, onAccessibilityToggle]);

  // PanResponder on the whole container.
  // - `onMoveShouldSetPanResponder` only claims the gesture when it reads
  //   as horizontal (|dx| dominates |dy|) so vertical drags pass through
  //   to the parent ScrollView.
  // - A near-zero-travel release counts as a tap and fires the
  //   side-appropriate onPress callback (zoom viewer). Drag releases
  //   leave the divider at its current position.
  // - `onPanResponderTerminationRequest` returns true so ScrollView can
  //   reclaim mid-gesture if the user flips direction.
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: (_evt, gs) =>
          Math.abs(gs.dx) > Math.abs(gs.dy) + DIRECTION_THRESHOLD_PX,
        onPanResponderTerminationRequest: () => true,
        onPanResponderGrant: (evt) => {
          gestureStartSplit.current = splitPosition.value;
          gestureStartX.current = evt.nativeEvent.locationX;
          hapticLight();
        },
        onPanResponderMove: (_evt, gestureState) => {
          const delta = gestureState.dx / sliderWidth;
          splitPosition.value = clamp(
            gestureStartSplit.current + delta,
            0,
            1,
          );
        },
        onPanResponderRelease: (_evt, gestureState) => {
          const travel =
            Math.abs(gestureState.dx) + Math.abs(gestureState.dy);
          if (travel > TAP_MAX_TRAVEL_PX) return;
          // Tap — decide which side the tap landed on based on the
          // divider at tap start.
          const tapRatio = clamp(
            gestureStartX.current / sliderWidth,
            0,
            1,
          );
          if (tapRatio <= splitPosition.value) {
            onPressAfterImage?.();
          } else {
            onPressBeforeImage?.();
          }
        },
      }),
    [sliderWidth, splitPosition, onPressAfterImage, onPressBeforeImage],
  );

  const afterOverlayStyle = useAnimatedStyle(() => ({
    width: splitPosition.value * sliderWidth,
  }));

  const dividerStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: splitPosition.value * sliderWidth - DIVIDER_WIDTH / 2 },
    ],
  }));

  // Label pills sit as siblings of the clip (not children of it) so each
  // label's position is anchored to full sliderWidth. Visibility is a
  // monotonic fade of splitPosition — BEFORE hides as the glow-up fills
  // the frame, GLOW UP appears as the glow-up reveals. This prevents
  // both pills rendering on the same visible half of the image.
  const beforeLabelStyle = useAnimatedStyle(() => ({
    opacity: 1 - splitPosition.value,
  }));
  const afterLabelStyle = useAnimatedStyle(() => ({
    opacity: splitPosition.value,
  }));

  return (
    <View
      style={[styles.container, { width: sliderWidth, height: sliderHeight }]}
      accessible={true}
      accessibilityRole="adjustable"
      accessibilityLabel={`Before and after comparison. ${rightLabel} on the right. Drag to compare.`}
      accessibilityHint="Drag or tap to reveal before and after. Activate to toggle."
      accessibilityActions={[
        { name: "activate", label: "Toggle between before and after" },
      ]}
      onAccessibilityAction={(event) => {
        if (event.nativeEvent.actionName === "activate") {
          runOnJS(handleAccessibilityToggle)();
        }
      }}
      {...panResponder.panHandlers}
    >
      <Image
        source={{ uri: beforeUrl }}
        style={[styles.image, { width: sliderWidth, height: sliderHeight }]}
        resizeMode="cover"
        accessibilityLabel="Before photo"
      />

      <Animated.View
        style={[styles.afterClip, { height: sliderHeight }, afterOverlayStyle]}
        pointerEvents="none"
      >
        <Image
          source={{ uri: afterUrl }}
          style={[styles.image, { width: sliderWidth, height: sliderHeight }]}
          resizeMode="cover"
          accessibilityLabel={`${rightLabel} result photo`}
        />
      </Animated.View>

      <Animated.View
        style={[styles.dividerContainer, dividerStyle]}
        pointerEvents="none"
      >
        <View style={styles.dividerLine} />

        <View
          style={[
            styles.handle,
            {
              borderColor: theme.accent,
              shadowColor: theme.accent,
            },
          ]}
        >
          <Ionicons
            name="chevron-back"
            size={14}
            color={theme.accent}
          />
          <Ionicons
            name="chevron-forward"
            size={14}
            color={theme.accent}
          />
        </View>
      </Animated.View>

      {/* Labels live outside the clip so their horizontal position is
          stable; opacity reflects which side of the image is visible. */}
      <Animated.View
        pointerEvents="none"
        style={[styles.labelBadge, styles.labelBadgeLeft, beforeLabelStyle]}
      >
        <Label color="primary">BEFORE</Label>
      </Animated.View>
      <Animated.View
        pointerEvents="none"
        style={[
          styles.labelBadge,
          styles.labelBadgeRight,
          { backgroundColor: theme.accent + "CC" },
          afterLabelStyle,
        ]}
      >
        <Label color={THEME.colors.white}>{rightLabel.toUpperCase()}</Label>
      </Animated.View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    borderRadius: THEME.radius.lg,
    borderCurve: "continuous",
    overflow: "hidden",
    alignSelf: "center",
  },
  image: {
    position: "absolute",
    top: 0,
    left: 0,
  },
  afterClip: {
    position: "absolute",
    top: 0,
    left: 0,
    overflow: "hidden",
  },
  dividerContainer: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: HANDLE_SIZE + HANDLE_HIT_PADDING,
    alignItems: "center",
    justifyContent: "center",
  },
  dividerLine: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: DIVIDER_WIDTH,
    backgroundColor: THEME.colors.white,
    opacity: 0.9,
  },
  handle: {
    width: HANDLE_SIZE,
    height: HANDLE_SIZE,
    borderRadius: HANDLE_SIZE / 2,
    borderWidth: GLOW_RING_WIDTH,
    backgroundColor: THEME.colors.glass,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 2,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
    elevation: 6,
  },
  labelBadge: {
    position: "absolute",
    bottom: THEME.spacing.md,
    backgroundColor: "rgba(0,0,0,0.55)",
    paddingHorizontal: THEME.spacing.md,
    paddingVertical: THEME.spacing.xs + 2,
    borderRadius: THEME.radius.sm,
    borderCurve: "continuous",
  },
  labelBadgeLeft: {
    left: THEME.spacing.md,
  },
  labelBadgeRight: {
    right: THEME.spacing.md,
  },
});
