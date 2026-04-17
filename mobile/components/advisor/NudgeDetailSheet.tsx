/**
 * NudgeDetailSheet — bottom sheet showing a single nudge's full content.
 *
 * The feed card truncates body copy at three lines; tapping a card opens
 * this sheet so the user can read the whole nudge without surrounding
 * chrome. Intentionally minimal — no actions beyond close — to match
 * the nudge's passive-broadcast nature.
 */
import { useCallback } from "react";
import { Modal, Pressable, ScrollView, StyleSheet, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { THEME } from "../../constants/theme";
import { useTheme } from "../../lib/theme-context";
import { Body, Caption, Heading } from "../ui/Text";
import { formatTimeAgo } from "../../lib/format";
import { MIN_TOUCH_TARGET } from "../../constants/config";
import type { Nudge } from "../../lib/advisor";

interface NudgeDetailSheetProps {
  nudge: Nudge | null;
  onClose: () => void;
}

function nudgeLabel(trigger: string): string {
  const labels: Record<string, string> = {
    post_analysis: "Post Analysis",
    weekly_checkin: "Weekly Check-in",
    milestone: "Milestone",
    re_engagement: "Welcome Back",
    check_in: "Check-in",
    tip: "Tip",
    reminder: "Reminder",
    welcome: "Welcome",
    outfit_post: "Outfit Post",
  };
  return (
    labels[trigger] ??
    trigger
      .replace(/_/g, " ")
      .replace(/\b\w/g, (c) => c.toUpperCase())
  );
}

function nudgeIcon(trigger: string): React.ComponentProps<typeof Ionicons>["name"] {
  switch (trigger) {
    case "post_analysis":
      return "bulb-outline";
    case "weekly_checkin":
    case "check_in":
      return "chatbubble-outline";
    case "milestone":
      return "trophy-outline";
    case "re_engagement":
      return "sparkles-outline";
    case "reminder":
      return "alarm-outline";
    default:
      return "bulb-outline";
  }
}

export function NudgeDetailSheet({ nudge, onClose }: NudgeDetailSheetProps) {
  const { theme } = useTheme();
  const handleBackdropPress = useCallback(() => onClose(), [onClose]);

  return (
    <Modal
      visible={nudge !== null}
      animationType="fade"
      transparent
      onRequestClose={onClose}
      statusBarTranslucent
    >
      {/* Backdrop — tappable to dismiss; `pointerEvents` ensures the
          child card absorbs its own taps without propagating. */}
      <Pressable
        style={styles.backdrop}
        onPress={handleBackdropPress}
        accessibilityLabel="Dismiss nudge"
        accessibilityRole="button"
      />
      <SafeAreaView
        style={styles.sheetContainer}
        edges={["bottom"]}
        pointerEvents="box-none"
      >
        <View style={styles.sheet}>
          <View style={styles.header}>
            <View
              style={[
                styles.iconContainer,
                { backgroundColor: theme.accentMuted },
              ]}
            >
              <Ionicons
                name={nudge ? nudgeIcon(nudge.trigger) : "bulb-outline"}
                size={22}
                color={theme.accent}
              />
            </View>
            <View style={styles.titleColumn}>
              <Heading size="md" display={false}>
                {nudge ? nudgeLabel(nudge.trigger) : ""}
              </Heading>
              {nudge && (
                <Caption color="muted">
                  {formatTimeAgo(nudge.created_at)}
                </Caption>
              )}
            </View>
            <Pressable
              onPress={onClose}
              style={styles.closeButton}
              accessibilityLabel="Close"
              accessibilityRole="button"
              hitSlop={8}
            >
              <Ionicons
                name="close"
                size={22}
                color={THEME.colors.textSecondary}
              />
            </Pressable>
          </View>

          <ScrollView
            style={styles.body}
            contentContainerStyle={styles.bodyContent}
            showsVerticalScrollIndicator={false}
          >
            <Body color="primary" style={styles.bodyText}>
              {nudge?.content ?? ""}
            </Body>
          </ScrollView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0, 0, 0, 0.65)",
  },
  sheetContainer: {
    flex: 1,
    justifyContent: "flex-end",
  },
  sheet: {
    backgroundColor: THEME.colors.bg,
    borderTopLeftRadius: THEME.radius.xl,
    borderTopRightRadius: THEME.radius.xl,
    borderCurve: "continuous",
    paddingTop: THEME.spacing.lg,
    paddingHorizontal: THEME.spacing.lg,
    paddingBottom: THEME.spacing.lg,
    maxHeight: "80%",
    borderTopWidth: StyleSheet.hairlineWidth,
    borderLeftWidth: StyleSheet.hairlineWidth,
    borderRightWidth: StyleSheet.hairlineWidth,
    borderColor: THEME.colors.glassBorder,
  },
  header: {
    flexDirection: "row",
    alignItems: "center",
    gap: THEME.spacing.md,
    marginBottom: THEME.spacing.md,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  titleColumn: {
    flex: 1,
    gap: THEME.spacing.xs / 2,
  },
  closeButton: {
    width: MIN_TOUCH_TARGET,
    height: MIN_TOUCH_TARGET,
    alignItems: "center",
    justifyContent: "center",
  },
  body: {
    flexGrow: 0,
  },
  bodyContent: {
    paddingVertical: THEME.spacing.sm,
  },
  bodyText: {
    lineHeight: 22,
  },
});
