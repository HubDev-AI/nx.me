/**
 * BeforeAfterSlider — draggable split-view comparison slider.
 *
 * Entrance: spring from 0 → 0.5 on mount (~600ms).
 * Interaction: PanResponder drag to reposition the split anywhere 0–1.
 * Accessibility: VoiceOver custom action fires onAccessibilityToggle.
 * Brand: glow-ring handle uses session accent colour from useTheme().
 */
import { useRef, useCallback } from "react";
import {
  View,
  Image,
  PanResponder,
  StyleSheet,
  Dimensions,
  Text,
} from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  clamp,
  runOnJS,
} from "react-native-reanimated";

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const { width: SCREEN_WIDTH } = Dimensions.get("window");

/** Horizontal padding applied on each side (matches BeforeAfterReveal). */
const H_PADDING = THEME.spacing.xl * 2;

/** Full-width slider: stretches edge-to-edge within the parent container. */
const SLIDER_WIDTH = SCREEN_WIDTH - H_PADDING;

/** Aspect ratio: portrait 3:4 (same as existing image cards). */
const SLIDER_HEIGHT = (SLIDER_WIDTH * 4) / 3;

/** Width of the draggable divider line. */
const DIVIDER_WIDTH = 2;

/** Diameter of the circular drag handle. */
const HANDLE_SIZE = 36;

/** Thickness of the glow-ring on the handle (brand accent). */
const GLOW_RING_WIDTH = 2;

/** Spring config for entrance animation (~600ms with these values). */
const ENTRANCE_SPRING = {
  damping: 15,
  stiffness: 150,
  mass: 1,
} as const;

/** Label strip height for BEFORE / right label badges. */
const LABEL_BADGE_PADDING_H = THEME.spacing.md;
const LABEL_BADGE_PADDING_V = THEME.spacing.xs + 2;

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
  /** Entrance spring duration hint (ms). Default 600. The spring physics
   * control the actual timing; this parameter is stored for documentation
   * purposes but the spring constants above govern the motion. */
  entranceDurationMs?: number;
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
  entranceDurationMs: _entranceDurationMs = 600,
  onAccessibilityToggle,
}: BeforeAfterSliderProps) {
  const { theme } = useTheme();

  // splitPosition: 0 = all before, 1 = all after.
  // Starts at 0, springs to initialSplit on mount (entrance animation).
  const splitPosition = useSharedValue(0);

  // Track the split at gesture start so we can add delta on top.
  const gestureStartSplit = useRef(0);

  // Kick off entrance animation.
  // useSharedValue initial value is 0; withSpring to initialSplit on first render.
  // This runs once — the ref guards against repeat calls.
  const entranceStarted = useRef(false);
  if (!entranceStarted.current) {
    entranceStarted.current = true;
    splitPosition.value = withSpring(initialSplit, ENTRANCE_SPRING);
  }

  const handleAccessibilityToggle = useCallback(() => {
    // Toggle between 0.25 (mostly before) and 0.75 (mostly after).
    const current = splitPosition.value;
    splitPosition.value = withSpring(current > 0.5 ? 0.25 : 0.75, ENTRANCE_SPRING);
    onAccessibilityToggle?.();
  }, [splitPosition, onAccessibilityToggle]);

  const panResponder = useRef(
    PanResponder.create({
      onStartShouldSetPanResponder: () => true,
      onMoveShouldSetPanResponder: () => true,
      onPanResponderGrant: () => {
        gestureStartSplit.current = splitPosition.value;
      },
      onPanResponderMove: (_evt, gestureState) => {
        const delta = gestureState.dx / SLIDER_WIDTH;
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
  ).current;

  // Animated style for the right (after) image overlay: clips width to 1-split.
  const afterOverlayStyle = useAnimatedStyle(() => ({
    width: splitPosition.value * SLIDER_WIDTH,
  }));

  // Animated style for the divider + handle: moves left edge to split position.
  const dividerStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: splitPosition.value * SLIDER_WIDTH - DIVIDER_WIDTH / 2 },
    ],
  }));

  return (
    <View
      style={styles.container}
      accessible={true}
      accessibilityRole="adjustable"
      accessibilityLabel={`Before and after comparison. ${rightLabel} result on the right. Drag to compare.`}
      accessibilityHint="Drag left or right to reveal before and after images. Activate to toggle."
      accessibilityActions={[
        { name: "activate", label: "Toggle between before and after" },
      ]}
      onAccessibilityAction={(event) => {
        if (event.nativeEvent.actionName === "activate") {
          runOnJS(handleAccessibilityToggle)();
        }
      }}
    >
      {/* Before image — full width base layer */}
      <Image
        source={{ uri: beforeUrl }}
        style={styles.image}
        resizeMode="cover"
        accessibilityLabel="Before photo"
      />

      {/* After image — clipped to left portion via overflow:hidden wrapper */}
      <Animated.View style={[styles.afterClip, afterOverlayStyle]} pointerEvents="none">
        <Image
          source={{ uri: afterUrl }}
          style={[styles.image, styles.afterImage]}
          resizeMode="cover"
          accessibilityLabel={`${rightLabel} result photo`}
        />
        {/* Right (after) label badge */}
        <View style={[styles.labelBadge, styles.labelBadgeRight, { backgroundColor: theme.accent + "CC" }]}>
          <Text style={[styles.labelText, styles.labelTextAfter]}>
            {rightLabel.toUpperCase()}
          </Text>
        </View>
      </Animated.View>

      {/* Draggable divider + handle — sits on top, receives touch */}
      <Animated.View style={[styles.dividerContainer, dividerStyle]} {...panResponder.panHandlers}>
        {/* Vertical divider line */}
        <View style={styles.dividerLine} />

        {/* Drag handle */}
        <View
          style={[
            styles.handle,
            {
              borderColor: theme.accent,
              shadowColor: theme.accent,
            },
          ]}
        >
          {/* Left arrow */}
          <Text style={[styles.handleArrow, { color: theme.accent }]}>‹</Text>
          {/* Right arrow */}
          <Text style={[styles.handleArrow, { color: theme.accent }]}>›</Text>
        </View>
      </Animated.View>

      {/* Before label badge — always visible in bottom-left */}
      <View style={[styles.labelBadge, styles.labelBadgeLeft]}>
        <Text style={styles.labelText}>BEFORE</Text>
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    width: SLIDER_WIDTH,
    height: SLIDER_HEIGHT,
    borderRadius: THEME.radius.lg,
    overflow: "hidden",
    alignSelf: "center",
  },
  image: {
    width: SLIDER_WIDTH,
    height: SLIDER_HEIGHT,
    position: "absolute",
    top: 0,
    left: 0,
  },
  afterClip: {
    position: "absolute",
    top: 0,
    left: 0,
    height: SLIDER_HEIGHT,
    overflow: "hidden",
  },
  afterImage: {
    // Same absolute position within the clipped container.
  },
  dividerContainer: {
    position: "absolute",
    top: 0,
    bottom: 0,
    width: HANDLE_SIZE + 24, // extended hit area for touch
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
    borderRadius: THEME.radius.pill,
    borderWidth: GLOW_RING_WIDTH,
    backgroundColor: THEME.colors.glass,
    alignItems: "center",
    justifyContent: "center",
    flexDirection: "row",
    gap: 2,
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.5,
    shadowRadius: 8,
    elevation: 6,
  },
  handleArrow: {
    fontSize: 16,
    fontFamily: FONTS.bodyBold,
    lineHeight: 18,
    includeFontPadding: false,
  },
  labelBadge: {
    position: "absolute",
    bottom: THEME.spacing.md,
    backgroundColor: "rgba(0,0,0,0.55)",
    paddingHorizontal: LABEL_BADGE_PADDING_H,
    paddingVertical: LABEL_BADGE_PADDING_V,
    borderRadius: THEME.radius.sm,
  },
  labelBadgeLeft: {
    left: THEME.spacing.md,
  },
  labelBadgeRight: {
    // Stays at bottom-right within the after clip — but clip overflows so we
    // pin it to right edge of full container with pointerEvents="none" on parent.
    right: THEME.spacing.md,
  },
  labelText: {
    fontFamily: FONTS.bodyBold,
    fontSize: 13,
    color: THEME.colors.textPrimary,
    letterSpacing: 1,
  },
  labelTextAfter: {
    color: THEME.colors.white,
  },
});
