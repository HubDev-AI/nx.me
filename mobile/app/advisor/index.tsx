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
  StyleSheet,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { PressableScale } from "../../components/ui/PressableScale";
import { useTheme } from "../../lib/theme-context";
import { hapticLight } from "../../lib/haptics";
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
  const { theme } = useTheme();

  const handleTabChange = useCallback((tab: AdvisorTab) => {
    hapticLight();
    setActiveTab(tab);
  }, []);

  return (
    <View style={styles.container}>
      <PageBackground overlayOpacity={0.88} />

      {/* Tab bar */}
      <View style={styles.tabBar} accessibilityRole="tablist">
        {TABS.map((tab) => {
          const isActive = activeTab === tab.key;
          return (
            <PressableScale
              key={tab.key}
              scale={0.94}
              haptic={false}
              onPress={() => handleTabChange(tab.key)}
              style={[
                styles.tab,
                isActive && {
                  backgroundColor: theme.accent + "1A",
                  borderColor: theme.accent,
                  ...THEME.shadow.glow(theme.accent),
                },
              ]}
              accessibilityLabel={`${tab.label} tab`}
              accessibilityRole="tab"
              accessibilityState={{ selected: isActive }}
            >
              <Ionicons
                name={isActive ? tab.iconFocused : tab.icon}
                size={18}
                color={isActive ? theme.accent : THEME.colors.textSecondary}
              />
              <Text style={[styles.tabLabel, isActive && { color: theme.accent, fontFamily: FONTS.bodySemiBold }]}>
                {tab.label}
              </Text>
            </PressableScale>
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
  tabBar: {
    flexDirection: "row",
    paddingHorizontal: THEME.spacing.xl,
    paddingVertical: THEME.spacing.md,
    marginTop: THEME.spacing.sm,
    marginBottom: THEME.spacing.xs,
    gap: THEME.spacing.sm,
    backgroundColor: "transparent",
  },
  tab: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "center",
    gap: THEME.spacing.sm,
    paddingVertical: THEME.spacing.sm + 2,
    borderRadius: THEME.radius.pill,
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    minHeight: MIN_TOUCH_TARGET,
    ...THEME.shadow.glass,
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
