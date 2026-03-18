/**
 * SuggestionPills — staggered entrance animation for suggestion list items.
 * Each pill slides up from below with a spring + delay offset.
 * Respects reduced-motion preference.
 */
import { useState, useEffect } from "react";
import { View, Text, StyleSheet, AccessibilityInfo } from "react-native";
import Animated, {
  FadeIn,
  FadeInUp,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import {
  BG_ELEVATED,
  TEXT_PRIMARY,
  CTA_PRIMARY,
} from "../../constants/colors";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STAGGER_DELAY_MS = 80;
const PILL_DURATION_MS = 250;
const SPRING_CONFIG = { damping: 16, stiffness: 140 };

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SuggestionPillsProps {
  suggestions: string[];
  /** Whether the reveal animation has completed (triggers stagger start) */
  visible: boolean;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function SuggestionPills({
  suggestions,
  visible,
}: SuggestionPillsProps) {
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    AccessibilityInfo.isReduceMotionEnabled().then(setReducedMotion);
  }, []);

  if (!visible || suggestions.length === 0) return null;

  return (
    <View
      style={styles.container}
      accessibilityRole="list"
      accessibilityLabel="Style suggestions"
    >
      <Animated.Text
        entering={reducedMotion ? FadeIn.duration(100) : FadeIn.duration(200)}
        style={styles.heading}
      >
        Suggestions
      </Animated.Text>
      {suggestions.map((suggestion, index) => {
        const entering = reducedMotion
          ? FadeIn.duration(100)
          : FadeInUp.delay(index * STAGGER_DELAY_MS)
              .duration(PILL_DURATION_MS)
              .springify()
              .damping(SPRING_CONFIG.damping)
              .stiffness(SPRING_CONFIG.stiffness);

        return (
          <Animated.View
            key={`${index}-${suggestion}`}
            entering={entering}
            style={styles.pill}
            accessibilityRole="text"
          >
            <Ionicons
              name="sparkles-outline"
              size={16}
              color={CTA_PRIMARY}
              style={styles.pillIcon}
            />
            <Text style={styles.pillText}>{suggestion}</Text>
          </Animated.View>
        );
      })}
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const SPACING = 8;

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: SPACING * 2,
    paddingTop: SPACING * 2,
    gap: SPACING,
  },
  heading: {
    fontSize: 16,
    fontWeight: "700",
    color: TEXT_PRIMARY,
    marginBottom: SPACING / 2,
  },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: BG_ELEVATED,
    borderRadius: 12,
    paddingVertical: SPACING * 1.5,
    paddingHorizontal: SPACING * 2,
    minHeight: 44,
  },
  pillIcon: {
    marginRight: SPACING,
  },
  pillText: {
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
    color: TEXT_PRIMARY,
  },
});
