import { useCallback } from "react";
import { View, Pressable, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  TEXT_SECONDARY,
  BG_PAGE,
} from "../../constants/colors";
import { THEME } from "../../constants/theme";
import { FEED_SORT } from "../../constants/config";
import type { FeedSortValue } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";
import { useTheme } from "../../lib/theme-context";

const MIN_TOUCH_TARGET = 44;

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
  const handlePress = useCallback(() => {
    onPress(option.value);
  }, [onPress, option.value]);

  return (
    <Pressable
      onPress={handlePress}
      style={[
        styles.tab,
        isActive && {
          backgroundColor: accent + "1A",
          borderColor: accent,
        },
      ]}
      accessibilityRole="tab"
      accessibilityState={{ selected: isActive }}
      accessibilityLabel={`Sort by ${option.label}`}
    >
      <Ionicons
        name={option.icon}
        size={16}
        color={isActive ? accent : TEXT_SECONDARY}
      />
      <Text style={[styles.tabLabel, isActive && { color: accent }]}>
        {option.label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    gap: 10,
    paddingHorizontal: 20,
    paddingVertical: 12,
    backgroundColor: "transparent",
  },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 18,
    paddingVertical: 10,
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: 9999,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
  },
  tabLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: TEXT_SECONDARY,
  },
});
