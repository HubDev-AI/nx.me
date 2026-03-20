import { useCallback } from "react";
import { Pressable, Text, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { formatCount } from "../../lib/format";
import { hapticLight } from "../../lib/haptics";
import { FONTS } from "../../hooks/useFonts";

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
  const { theme } = useTheme();
  const scale = useSharedValue(1);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePressIn = useCallback(() => {
    scale.value = withSpring(0.96, THEME.animation.press);
  }, []);

  const handlePressOut = useCallback(() => {
    scale.value = withSpring(1, THEME.animation.press);
  }, []);

  const handlePress = useCallback(() => {
    hapticLight();
    onReact();
  }, [onReact]);

  const iconName = hasReacted ? "heart" : "heart-outline";
  const iconColor = hasReacted ? theme.accent : THEME.colors.textSecondary;
  const countColor = hasReacted ? theme.accent : THEME.colors.textSecondary;

  return (
    <Animated.View style={animatedStyle}>
      <Pressable
        onPress={handlePress}
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

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.xs,
    minHeight: MIN_TOUCH_TARGET,
    minWidth: MIN_TOUCH_TARGET,
    paddingHorizontal: THEME.spacing.xs,
    paddingVertical: THEME.spacing.sm,
  },
  count: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    fontWeight: "600",
  },
});
