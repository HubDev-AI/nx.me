/**
 * Advisor main screen — tabbed interface for Chat, Nudges, and Memories.
 *
 * Chat: premium-only conversation with Ada (shows PaywallModal on 402).
 * Nudges: Ada's tips and check-ins, available to all tiers.
 * Memories: user memories that Ada uses for personalisation.
 */
import { useState, useCallback } from "react";
import {
  View,
  Text,
  Pressable,
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { useTheme } from "../../lib/theme-context";
import { FONTS } from "../../hooks/useFonts";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import { ChatView } from "../../components/advisor/ChatView";
import { NudgeFeed } from "../../components/advisor/NudgeFeed";
import { MemoryList } from "../../components/advisor/MemoryList";

type AdvisorTab = "chat" | "nudges" | "memories";

interface TabConfig {
  key: AdvisorTab;
  label: string;
  icon: React.ComponentProps<typeof Ionicons>["name"];
  iconFocused: React.ComponentProps<typeof Ionicons>["name"];
}

const TABS: TabConfig[] = [
  {
    key: "chat",
    label: "Chat",
    icon: "chatbubble-outline",
    iconFocused: "chatbubble",
  },
  {
    key: "nudges",
    label: "Nudges",
    icon: "sparkles-outline",
    iconFocused: "sparkles",
  },
  {
    key: "memories",
    label: "Memories",
    icon: "bookmark-outline",
    iconFocused: "bookmark",
  },
];

export default function AdvisorScreen() {
  const [activeTab, setActiveTab] = useState<AdvisorTab>("chat");
  const insets = useSafeAreaInsets();
  const { theme } = useTheme();

  const handleTabChange = useCallback((tab: AdvisorTab) => {
    setActiveTab(tab);
  }, []);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <PageBackground overlayOpacity={0.88} />
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Ada</Text>
        <Text style={styles.headerSubtitle}>Your style advisor</Text>
      </View>

      {/* Tab bar */}
      <View style={styles.tabBar} accessibilityRole="tablist">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <Pressable
              key={tab.key}
              onPress={() => handleTabChange(tab.key)}
              style={[styles.tab, isActive && { backgroundColor: theme.accentMuted }]}
              accessibilityLabel={`${tab.label} tab`}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
            >
              <Ionicons
                name={isActive ? tab.iconFocused : tab.icon}
                size={20}
                color={isActive ? theme.accent : THEME.colors.textSecondary}
              />
              <Text style={[styles.tabLabel, isActive && { color: theme.accent, fontFamily: FONTS.bodySemiBold }]}>
                {tab.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* Content */}
      <View style={styles.content}>
        {activeTab === "chat" && <ChatView />}
        {activeTab === "nudges" && <NudgeFeed />}
        {activeTab === "memories" && <MemoryList />}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: THEME.colors.bg,
  },
  header: {
    paddingHorizontal: THEME.spacing.xl,
    paddingTop: THEME.spacing.sm,
    paddingBottom: THEME.spacing.xs,
  },
  headerTitle: {
    fontFamily: FONTS.display,
    ...THEME.typography.headingLg,
    color: THEME.colors.textPrimary,
  },
  headerSubtitle: {
    fontFamily: FONTS.body,
    ...THEME.typography.caption,
    color: THEME.colors.textSecondary,
    marginTop: THEME.spacing.xs / 2,
  },
  tabBar: {
    flexDirection: "row",
    paddingHorizontal: THEME.spacing.lg,
    paddingTop: THEME.spacing.md,
    paddingBottom: THEME.spacing.sm,
    gap: THEME.spacing.xs,
  },
  tab: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
    paddingVertical: THEME.spacing.md - 2,
    borderRadius: THEME.radius.sm,
    minHeight: MIN_TOUCH_TARGET,
  },
  tabLabel: {
    fontFamily: FONTS.bodyMedium,
    fontSize: 14,
    color: THEME.colors.textSecondary,
  },
  content: {
    flex: 1,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: THEME.colors.border,
  },
});
