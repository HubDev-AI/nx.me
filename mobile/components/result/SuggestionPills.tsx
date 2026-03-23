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

import { THEME } from "../../constants/theme";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

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
  const { theme } = useTheme();
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
              color={theme.accent}
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

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.lg,
    gap: THEME.spacing.sm,
  },
  heading: {
    fontFamily: FONTS.bodySemiBold,
    fontSize: 16,
    color: THEME.colors.textPrimary,
    marginBottom: THEME.spacing.xs,
  },
  pill: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: THEME.colors.glass,
    borderRadius: THEME.radius.md,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    paddingVertical: THEME.spacing.md,
    paddingHorizontal: THEME.spacing.lg,
    minHeight: 44,
  },
  pillIcon: {
    marginRight: THEME.spacing.sm,
  },
  pillText: {
    flex: 1,
    fontFamily: FONTS.body,
    ...THEME.typography.body,
    color: THEME.colors.textPrimary,
  },
});
