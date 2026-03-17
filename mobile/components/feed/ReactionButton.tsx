import { useRef, useCallback } from "react";
import { Pressable, Text, Animated, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  COLORS,
  CTA_PRIMARY,
  TEXT_SECONDARY,
  BG_ELEVATED,
} from "../../constants/colors";

const PRESS_SCALE = 0.9;
const ANIMATION_DURATION_MS = 150;
const MIN_TOUCH_TARGET = 44;

interface ReactionButtonProps {
  reactionCount: number;
  hasReacted: boolean;
  onReact: () => void;
  disabled?: boolean;
}

/**
 * Heart reaction button with optimistic UI.
 * Scales on press, toggles fill when reacted, shows count.
 */
export function ReactionButton({
  reactionCount,
  hasReacted,
  onReact,
  disabled = false,
}: ReactionButtonProps) {
  const scaleAnim = useRef(new Animated.Value(1)).current;

  const handlePressIn = useCallback(() => {
    Animated.timing(scaleAnim, {
      toValue: PRESS_SCALE,
      duration: ANIMATION_DURATION_MS,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const handlePressOut = useCallback(() => {
    Animated.timing(scaleAnim, {
      toValue: 1,
      duration: ANIMATION_DURATION_MS,
      useNativeDriver: true,
    }).start();
  }, [scaleAnim]);

  const iconName = hasReacted ? "heart" : "heart-outline";
  const iconColor = hasReacted ? CTA_PRIMARY : TEXT_SECONDARY;
  const countColor = hasReacted ? CTA_PRIMARY : TEXT_SECONDARY;

  return (
    <Animated.View style={{ transform: [{ scale: scaleAnim }] }}>
      <Pressable
        onPress={onReact}
        onPressIn={handlePressIn}
        onPressOut={handlePressOut}
        disabled={disabled}
        style={styles.container}
        hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
        accessibilityLabel={
          hasReacted
            ? `Liked, ${reactionCount} reactions`
            : `Like, ${reactionCount} reactions`
        }
        accessibilityRole="button"
        accessibilityState={{ disabled, selected: hasReacted }}
      >
        <Ionicons name={iconName} size={22} color={iconColor} />
        <Text style={[styles.count, { color: countColor }]}>
          {formatCount(reactionCount)}
        </Text>
      </Pressable>
    </Animated.View>
  );
}

/** Format large numbers compactly: 1200 -> 1.2k */
function formatCount(count: number): string {
  if (count >= 1_000_000) {
    return `${(count / 1_000_000).toFixed(1)}m`;
  }
  if (count >= 1_000) {
    return `${(count / 1_000).toFixed(1)}k`;
  }
  return String(count);
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    gap: 4,
    minHeight: MIN_TOUCH_TARGET,
    minWidth: MIN_TOUCH_TARGET,
    paddingHorizontal: 8,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: BG_ELEVATED,
  },
  count: {
    fontSize: 14,
    fontWeight: "600",
  },
});
