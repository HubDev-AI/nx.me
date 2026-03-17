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

import {
  BG_PAGE,
  TEXT_PRIMARY,
  TEXT_SECONDARY,
  CTA_PRIMARY,
  BORDER_DEFAULT,
} from "../../constants/colors";
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

  const handleTabChange = useCallback((tab: AdvisorTab) => {
    setActiveTab(tab);
  }, []);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Ada</Text>
        <Text style={styles.headerSubtitle}>Your style advisor</Text>
      </View>

      {/* Tab bar */}
      <View style={styles.tabBar}>
        {TABS.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <Pressable
              key={tab.key}
              onPress={() => handleTabChange(tab.key)}
              style={[styles.tab, isActive && styles.tabActive]}
              accessibilityLabel={`${tab.label} tab`}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
            >
              <Ionicons
                name={isActive ? tab.iconFocused : tab.icon}
                size={20}
                color={isActive ? CTA_PRIMARY : TEXT_SECONDARY}
              />
              <Text style={[styles.tabLabel, isActive && styles.tabLabelActive]}>
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
    backgroundColor: BG_PAGE,
  },
  header: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 4,
  },
  headerTitle: {
    fontSize: 28,
    fontWeight: "800",
    color: TEXT_PRIMARY,
  },
  headerSubtitle: {
    fontSize: 14,
    color: TEXT_SECONDARY,
    marginTop: 2,
  },
  tabBar: {
    flexDirection: "row",
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    gap: 4,
  },
  tab: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    paddingVertical: 10,
    borderRadius: 10,
    minHeight: MIN_TOUCH_TARGET,
  },
  tabActive: {
    backgroundColor: "rgba(244,63,94,0.08)",
  },
  tabLabel: {
    fontSize: 14,
    fontWeight: "500",
    color: TEXT_SECONDARY,
  },
  tabLabelActive: {
    color: CTA_PRIMARY,
    fontWeight: "600",
  },
  content: {
    flex: 1,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: BORDER_DEFAULT,
  },
});
