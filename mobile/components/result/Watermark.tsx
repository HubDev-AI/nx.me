/**
 * Watermark — subtle corner attribution mark for share composites.
 *
 * Designed to be crisp at 1080×1080 export resolution. Never scales with
 * accessibility font size (allowFontScaling=false). Font size is fixed
 * proportional to imageHeightPx for predictable rendering.
 */
import { View, Text, StyleSheet } from "react-native";

import { FONTS } from "../../hooks/useFonts";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Text content of the watermark. Single source of truth — no inline string. */
const WATERMARK_TEXT = "nxme.ai · AI";

/** Proportion of imageHeightPx used for font size calculation. */
const FONT_SIZE_RATIO = 0.03;

/** Minimum font size to remain legible. */
const FONT_SIZE_MIN = 10;

/** Maximum font size to stay subtle. */
const FONT_SIZE_MAX = 24;

/** Padding between watermark text and the image edge (at 1080px). */
const PADDING_ABSOLUTE = 16;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WatermarkProps {
  /** Corner to place the mark. Default "bottom-right". */
  position?: "bottom-right" | "bottom-left";
  /** Height of the host image in px (used for proportional font sizing). */
  imageHeightPx: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function Watermark({ position = "bottom-right", imageHeightPx }: WatermarkProps) {
  const fontSize = Math.min(
    FONT_SIZE_MAX,
    Math.max(FONT_SIZE_MIN, Math.round(imageHeightPx * FONT_SIZE_RATIO)),
  );

  return (
    <View
      style={[
        styles.container,
        position === "bottom-left" ? styles.positionBottomLeft : styles.positionBottomRight,
        { padding: PADDING_ABSOLUTE },
      ]}
      pointerEvents="none"
    >
      <Text
        style={[styles.text, { fontSize }]}
        allowFontScaling={false}
        selectable={false}
      >
        {WATERMARK_TEXT}
      </Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: {
    position: "absolute",
    bottom: 0,
  },
  positionBottomRight: {
    right: 0,
    alignItems: "flex-end",
  },
  positionBottomLeft: {
    left: 0,
    alignItems: "flex-start",
  },
  text: {
    fontFamily: FONTS.bodySemiBold,
    color: "rgba(255, 255, 255, 0.55)",
    letterSpacing: 0.5,
    includeFontPadding: false,
  },
});
