import { useCallback } from "react";
import { View, Pressable, Text, StyleSheet } from "react-native";
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
} from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { FEED_SORT, MIN_TOUCH_TARGET } from "../../constants/config";
import type { FeedSortValue } from "../../constants/config";
import { hapticLight } from "../../lib/haptics";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

interface SortTabConfig {
  value: FeedSortValue;
  label: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
}

const SORT_OPTIONS: SortTabConfig[] = [
  { value: FEED_SORT.NEWEST, label: "Newest", icon: "time-outline" },
  { value: FEED_SORT.TRENDING, label: "Trending", icon: "flame-outline" },
  {
    value: FEED_SORT.BIGGEST_IMPROVEMENTS,
    label: "Top",
    icon: "trending-up-outline",
  },
];

interface SortTabsProps {
  activeSort: FeedSortValue;
  onSortChange: (sort: FeedSortValue) => void;
}

/** Horizontal sort tab bar for feed — newest / trending / top */
export function SortTabs({ activeSort, onSortChange }: SortTabsProps) {
  const { theme } = useTheme();
  return (
    <View style={styles.container} accessibilityRole="tablist">
      {SORT_OPTIONS.map((option) => (
        <SortTab
          key={option.value}
          option={option}
          isActive={activeSort === option.value}
          onPress={onSortChange}
          accent={theme.accent}
        />
      ))}
    </View>
  );
}

interface SortTabProps {
  option: SortTabConfig;
  isActive: boolean;
  onPress: (value: FeedSortValue) => void;
  accent: string;
}

function SortTab({ option, isActive, onPress, accent }: SortTabProps) {
  const scale = useSharedValue(1);
  const pressStyle = useAnimatedStyle(() => ({
    transform: [{ scale: scale.value }],
  }));

  const handlePress = useCallback(() => {
    hapticLight();
    onPress(option.value);
  }, [onPress, option.value]);

  return (
    <Animated.View style={pressStyle}>
      <Pressable
        onPress={handlePress}
        onPressIn={() => { scale.value = withSpring(0.96, THEME.animation.press); }}
        onPressOut={() => { scale.value = withSpring(1, THEME.animation.press); }}
        style={[
          styles.tab,
          isActive && {
            backgroundColor: accent + "1A",
            borderColor: accent,
            ...THEME.shadow.glow(accent),
          },
        ]}
        accessibilityRole="tab"
        accessibilityState={{ selected: isActive }}
        accessibilityLabel={`Sort by ${option.label}`}
      >
        <Ionicons
          name={option.icon}
          size={16}
          color={isActive ? accent : THEME.colors.textSecondary}
        />
        <Text style={[styles.tabLabel, isActive && { color: accent }]}>
          {option.label}
        </Text>
      </Pressable>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    gap: THEME.spacing.sm + 2,
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.md,
    backgroundColor: "transparent",
  },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.sm,
    paddingHorizontal: THEME.spacing.lg + 2,
    paddingVertical: THEME.spacing.sm + 2,
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    ...THEME.shadow.glass,
  },
  tabLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: THEME.colors.textSecondary,
  },
});
