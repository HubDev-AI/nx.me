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
import { useCallback, useMemo, useRef } from "react";
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

/** Horizontal padding applied on each side (matches BeforeAfterReveal). */
const H_PADDING = THEME.spacing.xl * 2;

/** Aspect ratio: portrait 3:4 (same as existing image cards). */
const ASPECT_RATIO_H_OVER_W = 4 / 3;

/** Width of the draggable divider line (bumped from 2 → 3 for visibility). */
const DIVIDER_WIDTH = 3;

/** Diameter of the circular drag handle. */
const HANDLE_SIZE = 36;

/** Thickness of the glow-ring on the handle (brand accent). */
const GLOW_RING_WIDTH = 2;

/** Spring config for entrance + tap-to-jump animations. */
const TOUCH_SPRING = {
  damping: 18,
  stiffness: 240,
  mass: 1,
} as const;

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
  /** Default split position (0–1). Default 0.5. */
  initialSplit?: number;
  /** Called by VoiceOver accessibility action (toggles between 0.25 and 0.75). */
  onAccessibilityToggle?: () => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function BeforeAfterSlider({
  beforeUrl,
  afterUrl,
  rightLabel,
  initialSplit = 0.5,
  onAccessibilityToggle,
}: BeforeAfterSliderProps) {
  const { theme } = useTheme();
  const { width: windowWidth } = useWindowDimensions();
  const sliderWidth = windowWidth - H_PADDING;
  const sliderHeight = sliderWidth * ASPECT_RATIO_H_OVER_W;

  const splitPosition = useSharedValue(0);
  const gestureStartSplit = useRef(0);

  // Kick off entrance animation on first render.
  const entranceStarted = useRef(false);
  if (!entranceStarted.current) {
    entranceStarted.current = true;
    splitPosition.value = withSpring(initialSplit, ENTRANCE_SPRING);
  }

  const handleAccessibilityToggle = useCallback(() => {
    const current = splitPosition.value;
    splitPosition.value = withSpring(
      current > 0.5 ? 0.25 : 0.75,
      ENTRANCE_SPRING,
    );
    onAccessibilityToggle?.();
  }, [splitPosition, onAccessibilityToggle]);

  // PanResponder on the whole container: tap-to-jump + drag.
  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: (evt) => {
          const tapX = evt.nativeEvent.locationX;
          const target = clamp(tapX / sliderWidth, 0, 1);
          gestureStartSplit.current = target;
          splitPosition.value = withSpring(target, TOUCH_SPRING);
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
        onPanResponderRelease: () => {
          // No snap — leave at current position.
        },
      }),
    [sliderWidth, splitPosition],
  );

  const afterOverlayStyle = useAnimatedStyle(() => ({
    width: splitPosition.value * sliderWidth,
  }));

  const dividerStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: splitPosition.value * sliderWidth - DIVIDER_WIDTH / 2 },
    ],
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
        <View
          style={[
            styles.labelBadge,
            styles.labelBadgeRight,
            { backgroundColor: theme.accent + "CC" },
          ]}
        >
          <Label color={THEME.colors.white}>{rightLabel.toUpperCase()}</Label>
        </View>
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

      <View style={[styles.labelBadge, styles.labelBadgeLeft]}>
        <Label color="primary">BEFORE</Label>
      </View>
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
    width: HANDLE_SIZE + 24,
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
