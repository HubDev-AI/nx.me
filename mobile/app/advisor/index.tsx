/**
 * Advisor main screen — tabbed interface for Chat, Nudges, and Memories.
 *
 * Chat: premium-only conversation with Ada (shows PaywallModal on 402).
 * Nudges: Ada's tips and check-ins, available to all tiers.
 * Memories: user memories that Ada uses for personalisation.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { StyleSheet, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useLocalSearchParams, useRouter } from "expo-router";

import { THEME } from "../../constants/theme";
import { PageBackground } from "../../components/ui/PageBackground";
import { PressableScale } from "../../components/ui/PressableScale";
import { Caption } from "../../components/ui/Text";
import { useTheme } from "../../lib/theme-context";
import { hapticLight } from "../../lib/haptics";
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
  const router = useRouter();
  const rawParams = useLocalSearchParams<{ seedText?: string | string[] }>();
  // `useLocalSearchParams` can surface a param as `string | string[]`
  // (when the same key repeats). The nudge CTA only ever sets a single
  // value, so we normalise to the first string.
  const seedText: string | undefined = Array.isArray(rawParams.seedText)
    ? rawParams.seedText[0]
    : rawParams.seedText;

  // One-shot consumption: remember the seed the first time we see it,
  // then clear the route param so a tab switch away + back doesn't
  // re-seed the composer. The ChatView's own mount-time `useState`
  // initializer is what actually captures the text; clearing the URL
  // param here just prevents the param from re-arriving as a prop on
  // ChatView's next remount.
  const consumedSeedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!seedText) return;
    if (consumedSeedRef.current === seedText) return;
    consumedSeedRef.current = seedText;
    // A seed means the user explicitly invoked Ada — switch the tab
    // even if they were viewing Nudges when they tapped the CTA.
    setActiveTab("chat");
    // Drop the param so subsequent remounts of AdvisorScreen (background
    // kill + restore, deep-link back) don't re-seed the composer.
    router.setParams({ seedText: undefined });
  }, [seedText, router]);

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
              <Caption
                weight={isActive ? "semibold" : "medium"}
                color={isActive ? theme.accent : "secondary"}
              >
                {tab.label}
              </Caption>
            </PressableScale>
          );
        })}
      </View>

      {/* Content */}
      <View style={styles.content}>
        {activeTab === "chat" && <ChatView seedText={seedText} />}
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
    borderCurve: "continuous",
    backgroundColor: THEME.colors.glass,
    borderWidth: 1,
    borderColor: THEME.colors.glassBorder,
    minHeight: MIN_TOUCH_TARGET,
    ...THEME.shadow.glass,
  },
  content: {
    flex: 1,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: THEME.colors.border,
  },
});
