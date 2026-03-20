import { useCallback } from "react";
import { View, Pressable, Text, StyleSheet } from "react-native";
import { Ionicons } from "@expo/vector-icons";

import {
  CTA_PRIMARY,
  TEXT_SECONDARY,
  BG_ELEVATED,
  BG_PAGE,
} from "../../constants/colors";
import { FEED_SORT } from "../../constants/config";
import type { FeedSortValue } from "../../constants/config";
import { FONTS } from "../../hooks/useFonts";

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
  return (
    <View style={styles.container} accessibilityRole="tablist">
      {SORT_OPTIONS.map((option) => (
        <SortTab
          key={option.value}
          option={option}
          isActive={activeSort === option.value}
          onPress={onSortChange}
        />
      ))}
    </View>
  );
}

interface SortTabProps {
  option: SortTabConfig;
  isActive: boolean;
  onPress: (value: FeedSortValue) => void;
}

function SortTab({ option, isActive, onPress }: SortTabProps) {
  const handlePress = useCallback(() => {
    onPress(option.value);
  }, [onPress, option.value]);

  return (
    <Pressable
      onPress={handlePress}
      style={[styles.tab, isActive && styles.tabActive]}
      accessibilityRole="tab"
      accessibilityState={{ selected: isActive }}
      accessibilityLabel={`Sort by ${option.label}`}
    >
      <Ionicons
        name={option.icon}
        size={16}
        color={isActive ? CTA_PRIMARY : TEXT_SECONDARY}
      />
      <Text style={[styles.tabLabel, isActive && styles.tabLabelActive]}>
        {option.label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 10,
    backgroundColor: BG_PAGE,
  },
  tab: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 16,
    paddingVertical: 8,
    minHeight: MIN_TOUCH_TARGET,
    borderRadius: 9999,
    backgroundColor: "rgba(26, 26, 26, 0.8)",
    borderWidth: 1,
    borderColor: "rgba(255, 255, 255, 0.04)",
  },
  tabActive: {
    backgroundColor: "rgba(244, 63, 94, 0.10)",
    borderColor: CTA_PRIMARY,
    shadowColor: CTA_PRIMARY,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 4,
  },
  tabLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: TEXT_SECONDARY,
  },
  tabLabelActive: {
    color: CTA_PRIMARY,
  },
});
